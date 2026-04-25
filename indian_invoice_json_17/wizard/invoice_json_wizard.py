import base64
import json
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class InvoiceJsonWizard(models.TransientModel):
    _name = 'invoice.json.wizard'
    _description = 'Invoice JSON Wizard'

    json_type = fields.Selection([
        ('einvoice', 'e-Invoice JSON'),
        ('ewaybill', 'e-Way Bill JSON'),
    ], required=True, default='einvoice', string='JSON Type')

    move_ids = fields.Many2many('account.move', string='Invoices', readonly=True)

    preview_json = fields.Text(string='JSON Preview', readonly=True)
    file_data = fields.Binary(string='File', readonly=True)
    file_name = fields.Char(string='File Name', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        if active_ids:
            res['move_ids'] = [(6, 0, active_ids)]
        return res

    def _move_field(self, move, field_name, default=False):
        if field_name in move._fields:
            return move[field_name]
        return default

    # -----------------------------
    # Generic helpers
    # -----------------------------
    def _clean_text(self, value, limit=None):
        if hasattr(value, 'display_name'):
            value = value.display_name or ''
        value = str(value or '').strip()
        value = re.sub(r'\s+', ' ', value)
        return value[:limit] if limit else value

    def _clean_alnum(self, value, limit=None):
        value = re.sub(r'[^A-Za-z0-9/\-]', '', value or '')
        return value[:limit] if limit else value

    def _clean_gstin(self, value):
        value = self._clean_text(value).upper().replace(' ', '')
        return value[:15]

    def _float(self, value, digits=2):
        return round(float(value or 0.0), digits)

    def _date_str(self, value):
        return value.strftime('%d/%m/%Y') if value else ''

    def _extract_digits(self, value):
        digits = re.sub(r'\D', '', value or '')
        return digits

    def _pincode_int(self, partner):
        digits = self._extract_digits(partner.zip)
        return int(digits[:6]) if digits else 0

    def _state_code(self, partner):
        state = partner.state_id
        if state:
            tin = getattr(state, 'l10n_in_tin', False)
            if tin:
                tin_digits = self._extract_digits(str(tin))
                if tin_digits:
                    return int(tin_digits[:2])
            state_code = self._extract_digits(state.code)
            if state_code:
                return int(state_code[:2])
        gstin = self._clean_gstin(partner.vat)
        if len(gstin) >= 2 and gstin[:2].isdigit():
            return int(gstin[:2])
        return 0

    def _tax_rates(self, line):
        rates = [self._float(tax.amount) for tax in line.tax_ids.filtered(lambda t: t.amount_type == 'percent')]
        return rates or [0.0]

    def _hsn_code(self, line):
        return self._clean_text(
            getattr(line.product_id, 'l10n_in_hsn_code', False)
            or getattr(line.product_id, 'hsn_code', False)
            or line.product_id.default_code
            or ''
        )

    def _validate_common_invoice(self, move):
        if move.move_type not in ('out_invoice', 'out_refund', 'in_refund'):
            raise UserError(_('%s: only customer invoice / credit note / debit note style moves are supported.') % (move.display_name,))
        if move.state != 'posted':
            raise UserError(_('%s must be posted.') % move.display_name)
        if not move.invoice_date:
            raise UserError(_('%s: invoice date is required.') % move.display_name)
        if not move.company_id.partner_id.vat:
            raise UserError(_('%s: company GSTIN is required.') % move.display_name)
        if not move.partner_id.vat and move.partner_id.country_id.code == 'IN':
            raise UserError(_('%s: customer GSTIN is required for Indian buyer.') % move.display_name)
        if not move.company_id.partner_id.state_id:
            raise UserError(_('%s: company state is required.') % move.display_name)
        if not move.partner_id.state_id and move.partner_id.country_id.code == 'IN':
            raise UserError(_('%s: customer state is required.') % move.display_name)

        invoice_lines = self._get_valid_invoice_lines(move)
        if not invoice_lines:
            all_lines = move.invoice_line_ids
            debug_lines = []
            for line in all_lines:
                debug_lines.append(
                    "id=%s, name=%s, display_type=%s, product=%s, qty=%s, subtotal=%s" % (
                        line.id,
                        line.name or '',
                        line.display_type or '',
                        line.product_id.display_name if line.product_id else '',
                        line.quantity or 0.0,
                        line.price_subtotal or 0.0,
                    )
                )
            raise UserError(_(
                '%s: invoice lines are required.\n\nAll invoice_line_ids seen by system:\n%s'
            ) % (move.display_name, '\n'.join(debug_lines) or 'No lines found'))
    
    def _get_valid_invoice_lines(self, move):
        lines = move.invoice_line_ids.filtered(lambda l: l.display_type == 'product')
        if lines:
            return lines

        lines = move.line_ids.filtered(
            lambda l: l.display_type == 'product' and not l.exclude_from_invoice_tab
        )
        if lines:
            return lines

        return lines

    def _validate_ewaybill(self, move):
        self._validate_common_invoice(move)

        if move.move_type != 'out_invoice':
            raise UserError(_('%s: e-Way Bill JSON is intended for invoice documents only.') % move.display_name)

        distance = (
            self._move_field(move, 'l10n_in_distance')
        )
        if not distance:
            raise UserError(_('%s: Distance is required in the built-in e-Way Bill details on invoice.') % move.display_name)

        lines = self._get_valid_invoice_lines(move)
        if not any(self._hsn_code(line) and not self._hsn_code(line).startswith('99') for line in lines):
            raise UserError(_('%s: at least one goods HSN code is required for e-Way Bill JSON.') % move.display_name)
        
    def _doc_type_for_irn(self, move):
        if move.move_type == 'out_invoice':
            return 'INV'
        if move.move_type == 'out_refund':
            return 'CRN'
        if move.move_type == 'in_refund':
            return 'DBN'
        return 'INV'

    # -----------------------------
    # e-Invoice JSON
    # -----------------------------
    def _prepare_einvoice_item(self, line, index, move):
        taxes = self._tax_rates(line)
        gst_rate = max(taxes) if taxes else 0.0
        qty = self._float(line.quantity or 0.0, 3)
        unit_price = self._float(line.price_unit)
        gross_amt = self._float(qty * unit_price)
        discount = self._float(gross_amt - line.price_subtotal)
        assessable = self._float(line.price_subtotal)

        is_intrastate = self._state_code(move.company_id.partner_id) == self._state_code(move.partner_id)
        igst_amt = 0.0 if is_intrastate else self._float(sum(line.tax_ids.compute_all(line.price_unit * (1 - (line.discount or 0.0) / 100.0), quantity=line.quantity, currency=move.currency_id, product=line.product_id, partner=move.partner_id)['taxes'][i]['amount'] for i, tax in enumerate(line.tax_ids) if getattr(tax, 'tax_group_id', False) and 'IGST' in (tax.tax_group_id.name or '').upper()))
        cgst_amt = self._float(move.currency_id.round((line.price_total - line.price_subtotal - igst_amt) / 2.0)) if is_intrastate else 0.0
        sgst_amt = self._float(move.currency_id.round((line.price_total - line.price_subtotal - igst_amt) / 2.0)) if is_intrastate else 0.0

        return {
            'SlNo': str(index),
            'PrdDesc': self._clean_text(line.name or line.product_id.display_name, 300),
            'IsServc': 'Y' if (self._hsn_code(line).startswith('99')) else 'N',
            'HsnCd': self._clean_text(self._hsn_code(line), 8),
            'Qty': qty,
            'FreeQty': 0,
            'Unit': self._clean_text(line.product_uom_id.name or 'NOS', 8),
            'UnitPrice': unit_price,
            'TotAmt': gross_amt,
            'Discount': self._float(abs(discount)) if discount > 0 else 0.0,
            'PreTaxVal': 0,
            'AssAmt': assessable,
            'GstRt': self._float(gst_rate),
            'IgstAmt': igst_amt,
            'CgstAmt': cgst_amt,
            'SgstAmt': sgst_amt,
            'CesRt': 0,
            'CesAmt': 0,
            'CesNonAdvlAmt': 0,
            'StateCesRt': 0,
            'StateCesAmt': 0,
            'StateCesNonAdvlAmt': 0,
            'OthChrg': 0,
            'TotItemVal': self._float(line.price_total),
        }

    def _prepare_einvoice_payload(self, move):
        self._validate_common_invoice(move)
        seller = move.company_id.partner_id
        buyer = move.partner_id
        lines = self._get_valid_invoice_lines(move)
        item_list = [
            self._prepare_einvoice_item(line, idx, move)
            for idx, line in enumerate(lines, start=1)
        ]

        is_intrastate = self._state_code(seller) == self._state_code(buyer)
        total_tax = self._float(move.amount_tax)
        if is_intrastate:
            cgst_val = self._float(total_tax / 2.0)
            sgst_val = self._float(total_tax / 2.0)
            igst_val = 0.0
        else:
            cgst_val = 0.0
            sgst_val = 0.0
            igst_val = total_tax

        payload = {
            'Version': '1.1',
            'TranDtls': {
                'TaxSch': 'GST',
                'SupTyp': 'B2B',
                'RegRev': 'N',
                'EcmGstin': None,
                'IgstOnIntra': 'N',
            },
            'DocDtls': {
                'Typ': self._doc_type_for_irn(move),
                'No': self._clean_alnum(move.name or move.ref or move.payment_reference or '', 16),
                'Dt': self._date_str(move.invoice_date),
            },
            'SellerDtls': {
                'Gstin': self._clean_gstin(seller.vat),
                'LglNm': self._clean_text(seller.name, 100),
                'TrdNm': self._clean_text(seller.name, 100),
                'Addr1': self._clean_text(seller.street or seller.contact_address or '', 100),
                'Addr2': self._clean_text(seller.street2 or '', 100),
                'Loc': self._clean_text(seller.city or seller.state_id.name or '', 50),
                'Pin': self._pincode_int(seller),
                'Stcd': str(self._state_code(seller)).zfill(2),
                'Ph': self._clean_alnum(seller.phone or seller.mobile or '', 12),
                'Em': self._clean_text(seller.email or '', 100),
            },
            'BuyerDtls': {
                'Gstin': self._clean_gstin(buyer.vat) if buyer.country_id.code == 'IN' else 'URP',
                'LglNm': self._clean_text(buyer.name, 100),
                'TrdNm': self._clean_text(buyer.name, 100),
                'Pos': str(self._state_code(buyer)).zfill(2),
                'Addr1': self._clean_text(buyer.street or buyer.contact_address or '', 100),
                'Addr2': self._clean_text(buyer.street2 or '', 100),
                'Loc': self._clean_text(buyer.city or buyer.state_id.name or '', 50),
                'Pin': self._pincode_int(buyer),
                'Stcd': str(self._state_code(buyer)).zfill(2),
                'Ph': self._clean_alnum(buyer.phone or buyer.mobile or '', 12),
                'Em': self._clean_text(buyer.email or '', 100),
            },
            'ItemList': item_list,
            'ValDtls': {
                'AssVal': self._float(move.amount_untaxed),
                'CgstVal': self._float(cgst_val),
                'SgstVal': self._float(sgst_val),
                'IgstVal': self._float(igst_val),
                'CesVal': 0.0,
                'StCesVal': 0.0,
                'Discount': 0.0,
                'OthChrg': 0.0,
                'RndOffAmt': self._float(move.amount_total - (move.amount_untaxed + total_tax)),
                'TotInvVal': self._float(move.amount_total),
            },
        }
        return payload

    # -----------------------------
    # e-Way Bill JSON
    # -----------------------------
    def _prepare_ewaybill_item(self, line, move):
        taxes = self._tax_rates(line)
        gst_rate = max(taxes) if taxes else 0.0
        is_intrastate = self._state_code(move.company_id.partner_id) == self._state_code(move.partner_id)
        taxable = self._float(line.price_subtotal)
        tax_total = self._float(line.price_total - line.price_subtotal)
        cgst = self._float(tax_total / 2.0) if is_intrastate else 0.0
        sgst = self._float(tax_total / 2.0) if is_intrastate else 0.0
        igst = 0.0 if is_intrastate else tax_total
        return {
            'productName': self._clean_text(line.product_id.display_name or line.name, 100),
            'productDesc': self._clean_text(line.name or line.product_id.display_name, 200),
            'hsnCode': int(self._extract_digits(self._hsn_code(line) or '0') or '0'),
            'quantity': self._float(line.quantity, 3),
            'qtyUnit': self._clean_text(line.product_uom_id.name or 'NOS', 8),
            'taxableAmount': taxable,
            'cgstRate': self._float(gst_rate / 2.0 if is_intrastate else 0.0),
            'sgstRate': self._float(gst_rate / 2.0 if is_intrastate else 0.0),
            'igstRate': self._float(gst_rate if not is_intrastate else 0.0),
            'cessRate': 0.0,
        }

    def _prepare_ewaybill_payload(self, move):
        self._validate_ewaybill(move)

        seller = move.company_id.partner_id
        buyer = move.partner_id
        lines = self._get_valid_invoice_lines(move)
        items = [self._prepare_ewaybill_item(line, move) for line in lines]

        is_intrastate = self._state_code(seller) == self._state_code(buyer)
        total_tax = self._float(move.amount_tax)
        cgst_val = self._float(total_tax / 2.0) if is_intrastate else 0.0
        sgst_val = self._float(total_tax / 2.0) if is_intrastate else 0.0
        igst_val = 0.0 if is_intrastate else total_tax

        supply_type = (
            self._move_field(move, 'l10n_in_supply_type')
        )
        sub_supply_type = (
            self._move_field(move, 'l10n_in_sub_supply_type')
        )
        sub_supply_desc = (
            self._move_field(move, 'l10n_in_sub_supply_desc')
        )
        transaction_type = (
            self._move_field(move, 'l10n_in_transaction_type')
        )
        transporter_id = (
            self._move_field(move, 'l10n_in_transporter_id')
        )
        transporter_name = (
            self._move_field(move, 'l10n_in_transporter_name')
        )
        transport_mode = (
            self._move_field(move, 'l10n_in_transport_mode')
        )
        transport_distance = (
            self._move_field(move, 'l10n_in_distance')
        )
        transport_doc_no = (
            self._move_field(move, 'l10n_in_transport_doc_no')
        )
        transport_doc_date = (
            self._move_field(move, 'l10n_in_transport_doc_date')
        )
        vehicle_no = (
            self._move_field(move, 'l10n_in_vehicle_no')
        )
        vehicle_type = (
            self._move_field(move, 'l10n_in_vehicle_type')
            or self._move_field(move, 'ewaybill_vehicle_type')
            or 'R'
        )

        return {
            'supplyType': supply_type,
            'subSupplyType': sub_supply_type,
            'subSupplyDesc': self._clean_text(sub_supply_desc, 50),
            'docType': 'INV',
            'docNo': self._clean_alnum(move.name or move.ref or '', 16),
            'docDate': self._date_str(move.invoice_date),
            'fromGstin': self._clean_gstin(seller.vat),
            'fromTrdName': self._clean_text(seller.name, 100),
            'fromAddr1': self._clean_text(seller.street or seller.contact_address or '', 120),
            'fromAddr2': self._clean_text(seller.street2 or '', 120),
            'fromPlace': self._clean_text(seller.city or seller.state_id.name or '', 50),
            'fromPincode': self._pincode_int(seller),
            'actFromStateCode': self._state_code(seller),
            'fromStateCode': self._state_code(seller),
            'toGstin': self._clean_gstin(buyer.vat) if buyer.country_id.code == 'IN' else 'URP',
            'toTrdName': self._clean_text(buyer.name, 100),
            'toAddr1': self._clean_text(buyer.street or buyer.contact_address or '', 120),
            'toAddr2': self._clean_text(buyer.street2 or '', 120),
            'toPlace': self._clean_text(buyer.city or buyer.state_id.name or '', 50),
            'toPincode': self._pincode_int(buyer),
            'actToStateCode': self._state_code(buyer),
            'toStateCode': self._state_code(buyer),
            'transactionType': int(transaction_type),
            'otherValue': 0.0,
            'totalValue': self._float(move.amount_untaxed),
            'cgstValue': cgst_val,
            'sgstValue': sgst_val,
            'igstValue': igst_val,
            'cessValue': 0.0,
            'cessNonAdvolValue': 0.0,
            'totInvValue': self._float(move.amount_total),
            'transporterId': self._clean_text(transporter_id, 15),
            'transporterName': self._clean_text(transporter_name, 100),
            'transDocNo': self._clean_text(transport_doc_no, 15),
            'transMode': str(transport_mode),
            'transDistance': str(int(transport_distance or 0)),
            'transDocDate': self._date_str(transport_doc_date) if transport_doc_date else '',
            'vehicleNo': self._clean_text(vehicle_no, 20),
            'vehicleType': vehicle_type,
            'itemList': items,
        }

    def _prepare_payload(self):
        self.ensure_one()
        if not self.move_ids:
            raise UserError(_('Please select at least one invoice.'))
        payloads = []
        for move in self.move_ids:
            payloads.append(
                self._prepare_einvoice_payload(move) if self.json_type == 'einvoice'
                else self._prepare_ewaybill_payload(move)
            )
        return payloads

    def action_generate_preview(self):
        self.ensure_one()
        payload = self._prepare_payload()
        json_text = json.dumps(payload if len(payload) > 1 else payload[0], indent=4, ensure_ascii=False)
        file_name = 'einvoice_govt_schema.json' if self.json_type == 'einvoice' else 'ewaybill_govt_schema.json'
        if len(payload) > 1:
            file_name = file_name.replace('.json', '_bulk.json')
        self.write({
            'preview_json': json_text,
            'file_name': file_name,
            'file_data': base64.b64encode(json_text.encode('utf-8')),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate JSON'),
            'res_model': 'invoice.json.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def action_download_json(self):
        self.ensure_one()
        if not self.file_data:
            self.action_generate_preview()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=invoice.json.wizard&id=%s&field=file_data&filename_field=file_name&download=true' % self.id,
            'target': 'self',
        }


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_open_invoice_json_wizard(self):
        active_ids = self.env.context.get('active_ids', self.ids)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Generate JSON'),
            'res_model': 'invoice.json.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_move_ids': active_ids,
                'active_ids': active_ids,
                'active_model': 'account.move',
            },
        }
