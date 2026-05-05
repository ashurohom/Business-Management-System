import base64
from collections import OrderedDict
from io import BytesIO

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.model
    def _has_explicit_delivery_address_vals(self, vals):
        tracked_fields = (
            "billing_partner_id",
            "billing_customer_name",
            "billing_mobile",
            "bill_to_address",
            "bill_to_city",
            "bill_to_state_id",
            "bill_to_country",
            "bill_to_zip",
            "shipping_partner_id",
            "shipping_customer_name",
            "shipping_mobile",
            "ship_to_address",
            "ship_to_city",
            "ship_to_state_id",
            "ship_to_country",
            "ship_to_zip",
        )
        return any(vals.get(field) not in (False, None, "") for field in tracked_fields)

    def _get_default_cash_rounding(self):
        self.ensure_one()
        rounding_model = self.env["account.cash.rounding"].sudo()
        rounding = rounding_model.search(
            [
                ("name", "=", "Round to nearest 1"),
                ("company_id", "in", [self.company_id.id, False]),
            ],
            order="company_id desc, id desc",
            limit=1,
        )
        if rounding:
            return rounding

        company = self.company_id.sudo()
        profit_account = company.default_cash_difference_income_account_id
        loss_account = company.default_cash_difference_expense_account_id
        if not (profit_account and loss_account):
            return rounding_model.browse()

        return rounding_model.create({
            "name": "Round to nearest 1",
            "rounding": 1.0,
            "strategy": "add_invoice_line",
            "rounding_method": "HALF-UP",
            "profit_account_id": profit_account.id,
            "loss_account_id": loss_account.id,
        })

    def _apply_default_cash_rounding(self):
        for move in self.filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund") and not m.invoice_cash_rounding_id
        ):
            rounding = move._get_default_cash_rounding()
            if rounding:
                move.invoice_cash_rounding_id = rounding

    _DELIVERY_TYPES = [
        ("direct_delivery", "Direct Delivery"),
        ("ship_to_different", "Ship To Different"),
        ("third_party_delivery", "Third Party Delivery"),
    ]

    _INVOICE_XLSX_HEADERS = [
        "Product",
        "HSN/SAC Code",
        "SKU",
        "Customer Name",
        "GST Number",
        "Contact ID (Phone number 1)",
        "Contact Number (Phone number 2)",
        "Invoice Number",
        "Date",
        "Quantity",
        "UNIT (Unit of Measure)",
        "Unit Price (without tax)",
        "Discount",
        "CGST Rate Price",
        "SGST Rate Price",
        "IGST Rate Price",
        "CGST Rate",
        "SGST Rate",
        "IGST Rate",
        "Tax (Taxes)",
        "Unit Price Including Tax",
        "Total",
        "Rounding Amount",
        "Invoice Total Amount",
        "IRN Number",
        "E-Invoice ACK. NO.",
        "E-Invoice Date",
        "E-Invoice Amt",
        "E-Way bill No.",
        "E-Way bill Date",
        "E-way Amt",
        "Payment Method",
        "Shipping Id",
        "Shipping State",
        "Shipping Country",
        "Shipping Pincode",
        "Shipping Address",
        "BILL State",
        "BILL Country",
        "BILL Pincode",
        "BILLING Address",
        "Components",
        "Invoice Status",
    ]

    shipping_ids = fields.One2many(
        "shipping.management",
        "invoice_id",
        string="Shipments",
    )
    shipping_count = fields.Integer(
        string="Shipping Count",
        compute="_compute_shipping_count",
    )

    @api.depends("shipping_ids")
    def _compute_shipping_count(self):
        for move in self:
            move.shipping_count = len(move.shipping_ids)

    def action_open_shipping(self):
        self.ensure_one()
        shipping = self.env['shipping.management'].search([('invoice_id', '=', self.id)], limit=1)
        return {
            'type': 'ir.actions.act_window',
            'name': 'Shipping Management',
            'view_mode': 'form',
            'res_model': 'shipping.management',
            'res_id': shipping.id if shipping else False,
            'context': {'default_invoice_id': self.id},
        }


    bill_to_same_as_customer = fields.Boolean(
        string="Bill To Same as Customer Address",
        default=True,
        copy=False,
    )
    delivery_type = fields.Selection(
        selection=_DELIVERY_TYPES,
        string="Delivery Type",
        default="direct_delivery",
        copy=False,
    )
    billing_partner_id = fields.Many2one(
        "res.partner",
        string="Billing Partner",
        copy=False,
    )
    billing_customer_id = fields.Many2one(
        "res.partner",
        string="Billing Customer ID",
        related="billing_partner_id",
        readonly=False,
    )
    billing_customer_name = fields.Char(
        string="Billing Customer Name",
        copy=False,
    )
    billing_mobile = fields.Char(string="Billing Mobile", copy=False)
    invoice_date = fields.Date(default=fields.Date.context_today)
    ship_to_same_as_customer = fields.Boolean(
        string="Ship To Same as Customer Address",
        default=True,
        copy=False,
    )
    shipping_partner_id = fields.Many2one(
        "res.partner",
        string="Shipping Partner",
        copy=False,
    )
    shipping_customer_id = fields.Many2one(
        "res.partner",
        string="Shipping Customer ID",
        related="shipping_partner_id",
        readonly=False,
    )
    shipping_customer_name = fields.Char(
        string="Shipping Customer Name",
        copy=False,
    )
    shipping_mobile = fields.Char(string="Shipping Mobile", copy=False)
    bill_to_address = fields.Text(
        string="Bill To Address",
        copy=False,
    )
    bill_to_city = fields.Char(string="Bill To City", copy=False)
    bill_to_state_id = fields.Many2one("res.country.state", string="Bill To State", copy=False)
    bill_to_zip = fields.Char(string="Bill To PIN Code", copy=False)
    ship_to_address = fields.Text(
        string="Ship To Address",
        copy=False,
    )
    ship_to_city = fields.Char(string="Ship To City", copy=False)
    ship_to_state_id = fields.Many2one("res.country.state", string="Ship To State", copy=False)
    ship_to_zip = fields.Char(string="Ship To PIN Code", copy=False)

    # Backward compatibility for previously loaded views.
    bill_to_partner_id = fields.Many2one("res.partner", string="Bill To Partner", copy=False)
    ship_to_partner_id = fields.Many2one("res.partner", string="Ship To Partner", copy=False)
    bill_to_address_text = fields.Text(string="Bill To Address Text", compute="_compute_legacy_address_text")
    ship_to_address_text = fields.Text(string="Ship To Address Text", compute="_compute_legacy_address_text")
    shipping_state = fields.Char(string="Shipping State", compute="_compute_export_address_fields")
    shipping_country = fields.Char(string="Shipping Country", compute="_compute_export_address_fields")
    shipping_pincode = fields.Char(string="Shipping Pincode", compute="_compute_export_address_fields")
    shipping_address = fields.Text(string="Shipping Address", compute="_compute_export_address_fields")
    billing_state = fields.Char(string="Billing State", compute="_compute_export_address_fields")
    billing_country = fields.Char(string="Billing Country", compute="_compute_export_address_fields")
    billing_pincode = fields.Char(string="Billing Pincode", compute="_compute_export_address_fields")
    billing_address = fields.Text(string="Billing Address", compute="_compute_export_address_fields")

    # ─── Customer / Contact info ─────────────────────────────────────────────
    dw_customer_gstin = fields.Char(string="GST Number", copy=False)
    dw_contact_id = fields.Char(string="Contact ID", copy=False)
    dw_contact_number = fields.Char(string="Contact Number", copy=False)

    # ─── Address country (free-text from import) ─────────────────────────────
    bill_to_country = fields.Char(string="Bill To Country", copy=False)
    ship_to_country = fields.Char(string="Ship To Country", copy=False)

    # ─── Payment info ────────────────────────────────────────────────────────
    dw_payment_mode = fields.Char(string="Payment Method", copy=False)
    dw_bank_name = fields.Char(string="Bank Name", copy=False)
    dw_payment_reference = fields.Char(string="Payment Reference", copy=False)
    dw_payment_date_imported = fields.Date(string="Payment Date", copy=False)
    dw_shipping_id = fields.Char(string="Shipping Id", copy=False)

    # ─── E-Invoice fields ────────────────────────────────────────────────────
    dw_irn_number = fields.Char(string="E-Invoice IRN Number", copy=False)
    dw_ack_number = fields.Char(string="E-Invoice ACK No.", copy=False)
    dw_ack_date = fields.Date(string="E-Invoice Date", copy=False)
    dw_e_invoice_amount = fields.Float(string="E-Invoice Amount", copy=False, digits=(16, 2))

    # ─── E-Way Bill fields ───────────────────────────────────────────────────
    dw_eway_bill_number = fields.Char(string="E-Way Bill No.", copy=False)
    dw_eway_bill_date = fields.Date(string="E-Way Bill Date", copy=False)
    dw_eway_bill_amount = fields.Float(string="E-Way Bill Amount", copy=False, digits=(16, 2))

    # ─── Legacy / misc ───────────────────────────────────────────────────────
    dw_place_of_supply = fields.Char(string="Place of Supply", copy=False)
    dw_ecommerce_platform = fields.Char(string="E-Commerce Platform", copy=False)
    dw_platform_order_id = fields.Char(string="Platform Order ID", copy=False)
    dw_grand_total_imported = fields.Float(string="Imported Grand Total", copy=False, digits=(16, 2))

    # ─── Smart button: link to import log line ───────────────────────────────
    import_log_line_id = fields.Many2one(
        comodel_name="dw.invoice.import.log.line",
        string="Import Log Line",
        copy=False,
        readonly=True,
        ondelete="set null",
    )
    import_log_count = fields.Integer(
        string="Import Log",
        compute="_compute_import_log_count",
    )

    def _compute_import_log_count(self):
        for move in self:
            move.import_log_count = 1 if move.import_log_line_id else 0

    def action_open_import_log(self):
        """Smart button action: open the related import log batch form."""
        self.ensure_one()
        if not self.import_log_line_id:
            raise UserError("This invoice has no linked import log.")
        return {
            "type": "ir.actions.act_window",
            "res_model": "dw.invoice.import.log",
            "res_id": self.import_log_line_id.log_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_export_invoice_xlsx(self):
        invoices = self._get_invoice_export_records()
        if not invoices:
            raise UserError("Select at least one customer invoice to export.")
        file_content = invoices._generate_invoice_xlsx_file()
        filename = "customer_invoice_export_%s.xlsx" % fields.Date.context_today(self)
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(file_content),
            "res_model": "account.move",
            "res_id": invoices[:1].id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }

    def action_open_packing_order(self):
        self.ensure_one()
        if self.move_type != "out_invoice":
            raise UserError("Packing is only available for customer invoices.")

        packing = self.env["packing.order"].search([("invoice_id", "=", self.id)], limit=1)
        if not packing:
            from_partner, from_address, to_partner, to_address = self._get_packing_addresses()
            packing = self.env["packing.order"].create({
                "invoice_id": self.id,
                "from_partner_id": from_partner.id if from_partner else False,
                "from_address": from_address,
                "to_partner_id": to_partner.id if to_partner else False,
                "to_address": to_address,
                "packing_line_ids": [
                    (0, 0, {
                        "product_id": line.product_id.id,
                        "description": line.name,
                        "quantity": line.quantity,
                        "uom_id": line.product_uom_id.id,
                    })
                    for line in self.invoice_line_ids.filtered(
                        lambda l: not l.display_type and l.product_id
                    )
                ],
            })

        return {
            "type": "ir.actions.act_window",
            "name": "Packing",
            "res_model": "packing.order",
            "res_id": packing.id,
            "view_mode": "form",
            "target": "current",
        }

    def _get_address_text(self, prefix):
        self.ensure_one()
        state = getattr(self, f"{prefix}_state_id")
        parts = [
            getattr(self, f"{prefix}_address"),
            getattr(self, f"{prefix}_city"),
            state.name if state else False,
            getattr(self, f"{prefix}_country"),
            getattr(self, f"{prefix}_zip"),
        ]
        return "\n".join(part for part in parts if part)

    def _get_packing_addresses(self):
        self.ensure_one()
        company_partner = self.company_id.partner_id
        customer_partner = self.partner_id
        billing_partner = self.billing_partner_id or customer_partner
        shipping_partner = self.shipping_partner_id or customer_partner

        if self.delivery_type == "third_party_delivery":
            return (
                billing_partner,
                self._get_address_text("bill_to") or billing_partner.contact_address or "",
                shipping_partner,
                self._get_address_text("ship_to") or shipping_partner.contact_address or "",
            )

        if self.delivery_type == "ship_to_different":
            return (
                company_partner,
                company_partner.contact_address or "",
                shipping_partner,
                self._get_address_text("ship_to") or shipping_partner.contact_address or "",
            )

        return (
            company_partner,
            company_partner.contact_address or "",
            customer_partner,
            customer_partner.contact_address or "",
        )

    def _get_invoice_export_records(self):
        invoices = self.filtered(lambda move: move.move_type == "out_invoice")
        if invoices:
            return invoices

        active_ids = self.env.context.get("active_ids") or []
        if not active_ids and self.env.context.get("active_id"):
            active_ids = [self.env.context["active_id"]]
        if active_ids:
            invoices = self.browse(active_ids).filtered(lambda move: move.move_type == "out_invoice")
            if invoices:
                return invoices

        domain = self.env.context.get("active_domain") or self.env.context.get("domain") or []
        if isinstance(domain, str):
            domain = safe_eval(domain)
        if domain:
            return self.search(domain + [("move_type", "=", "out_invoice")])

        return self.env["account.move"]

    def _generate_invoice_xlsx_file(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        worksheet = workbook.add_worksheet("Invoice Export")

        header_format = workbook.add_format({
            "bold": True,
            "bg_color": "#D9E2F3",
            "border": 1,
            "text_wrap": True,
            "align": "center",
            "valign": "vcenter",
        })
        text_format = workbook.add_format({"border": 1, "valign": "top"})
        date_format = workbook.add_format({"border": 1, "num_format": "dd-mm-yyyy", "valign": "top"})
        number_format = workbook.add_format({"border": 1, "num_format": "0.00", "valign": "top"})

        worksheet.freeze_panes(1, 0)
        worksheet.set_row(0, 28)
        worksheet.set_column(0, 0, 24)
        worksheet.set_column(1, 2, 18)
        worksheet.set_column(3, 4, 24)
        worksheet.set_column(5, 6, 20)
        worksheet.set_column(7, 8, 16)
        worksheet.set_column(9, 23, 14)
        worksheet.set_column(24, 31, 18)
        worksheet.set_column(32, 40, 22)
        worksheet.set_column(41, 41, 50)

        for col, header in enumerate(self._INVOICE_XLSX_HEADERS):
            worksheet.write(0, col, header, header_format)

        row = 1
        for invoice in self.filtered(lambda move: move.move_type == "out_invoice"):
            invoice_lines = invoice._get_invoice_export_lines()
            for line in invoice_lines:
                bom = invoice._get_phantom_bom(line.product_id)
                if bom:
                    kit_name = line.product_id.display_name
                    component_rows = invoice._get_kit_component_export_rows(line, bom)
                    for component_row in component_rows:
                        row_values = invoice._prepare_invoice_xlsx_row(
                            line,
                            product_override=component_row["product"],
                            qty_override=component_row["quantity"],
                            uom_override=component_row["uom"],
                            components_override=f"Kit: {kit_name}",
                            financial_override=component_row["financials"],
                        )
                        for col, value in enumerate(row_values):
                            if col == 8 and value:
                                worksheet.write_datetime(row, col, value, date_format)
                            elif isinstance(value, (int, float)):
                                worksheet.write_number(row, col, value, number_format)
                            else:
                                worksheet.write(row, col, value or "", text_format)
                        row += 1
                else:
                    # Regular product export
                    row_values = invoice._prepare_invoice_xlsx_row(line)
                    for col, value in enumerate(row_values):
                        if col == 8 and value:
                            worksheet.write_datetime(row, col, value, date_format)
                        elif isinstance(value, (int, float)):
                            worksheet.write_number(row, col, value, number_format)
                        else:
                            worksheet.write(row, col, value or "", text_format)
                    row += 1

        if row == 1:
            raise UserError("No exportable invoice lines were found for the selected customer invoices.")

        workbook.close()
        output.seek(0)
        return output.read()

    def _get_invoice_export_lines(self):
        self.ensure_one()
        invoice_lines = self.invoice_line_ids.filtered(
            lambda line: line.display_type in (False, "product")
        )
        if invoice_lines:
            return invoice_lines
        return self.line_ids.filtered(
            lambda line: line.display_type in (False, "product")
            and not line.tax_line_id
            and not line.exclude_from_invoice_tab
        )

    def _prepare_invoice_xlsx_row(
        self,
        line,
        product_override=None,
        qty_override=None,
        uom_override=None,
        components_override=None,
        financial_override=None,
    ):
        self.ensure_one()
        tax_details = self._get_invoice_line_tax_details(line)

        product = product_override or line.product_id
        quantity = qty_override if qty_override is not None else line.quantity or 0.0
        uom = uom_override or line.product_uom_id

        if financial_override:
            price_unit = financial_override["price_unit"]
            discount = financial_override["discount"]
            cgst_amount = financial_override["cgst_amount"]
            sgst_amount = financial_override["sgst_amount"]
            igst_amount = financial_override["igst_amount"]
            cgst_rate = financial_override["cgst_rate"]
            sgst_rate = financial_override["sgst_rate"]
            igst_rate = financial_override["igst_rate"]
            tax_names = financial_override["tax_names"]
            unit_price_inc_tax = financial_override["unit_price_included"]
            total_inc_tax = financial_override["line_total_included"]
        else:
            price_unit = line.price_unit
            discount = line.discount
            cgst_amount = tax_details["cgst_amount"]
            sgst_amount = tax_details["sgst_amount"]
            igst_amount = tax_details["igst_amount"]
            cgst_rate = tax_details["cgst_rate"]
            sgst_rate = tax_details["sgst_rate"]
            igst_rate = tax_details["igst_rate"]
            tax_names = ", ".join(line.tax_ids.mapped("name"))
            unit_price_inc_tax = tax_details["unit_price_included"]
            total_inc_tax = tax_details["line_total_included"]

        return [
            product.display_name or product.name or line.name or "",
            line.hsn_code or product.l10n_in_hsn_code or "",
            product.default_code or "",
            self.partner_id.name or "",
            self.partner_id.vat or "",
            self.partner_id.phone or "",
            self.partner_id.mobile or "",
            self.name or "",
            self.invoice_date or False,
            quantity,
            uom.name or "",
            price_unit,
            discount,
            cgst_amount,
            sgst_amount,
            igst_amount,
            cgst_rate,
            sgst_rate,
            igst_rate,
            tax_names,
            unit_price_inc_tax,
            total_inc_tax,
            abs(sum(self.line_ids.filtered(lambda l: l.display_type == 'rounding').mapped('amount_currency'))),
            self.amount_total,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            self.invoice_payment_term_id.name or "",
            self.dw_shipping_id or "",
            self.shipping_state or "",
            self.shipping_country or "",
            self.shipping_pincode or "",
            self.shipping_address or "",
            self.billing_state or "",
            self.billing_country or "",
            self.billing_pincode or "",
            self.billing_address or "",
            components_override if components_override is not None else self._get_kit_components(line.product_id),
            {'posted': 'Posted', 'cancel': 'Cancelled', 'draft': 'Draft'}.get(self.state, self.state),
        ]

    def _get_kit_component_export_rows(self, line, bom):
        self.ensure_one()
        quantity = line.quantity or 0.0
        tax_details = self._get_invoice_line_tax_details(line)
        discount = line.discount or 0.0
        discount_factor = 1 - (discount / 100.0)
        tax_names = ", ".join(line.tax_ids.mapped("name"))

        components = []
        total_component_qty = 0.0
        for bom_line in bom.bom_line_ids:
            component_qty = quantity * bom_line.product_qty
            components.append({
                "product": bom_line.product_id,
                "uom": bom_line.product_uom_id,
                "quantity": component_qty,
            })
            total_component_qty += component_qty

        if not components:
            return []

        if not total_component_qty:
            total_component_qty = float(len(components))
            for component in components:
                component["quantity"] = component["quantity"] or 0.0

        totals_map = {
            "subtotal_excluded": line.price_subtotal or 0.0,
            "line_total_included": line.price_total or 0.0,
            "cgst_amount": tax_details["cgst_amount"],
            "sgst_amount": tax_details["sgst_amount"],
            "igst_amount": tax_details["igst_amount"],
        }
        allocated_sums = {key: 0.0 for key in totals_map}

        for index, component in enumerate(components):
            is_last = index == len(components) - 1
            ratio = (component["quantity"] / total_component_qty) if total_component_qty else 0.0

            allocated = {}
            for key, total_value in totals_map.items():
                if is_last:
                    allocated_value = total_value - allocated_sums[key]
                else:
                    allocated_value = self.currency_id.round(total_value * ratio)
                    allocated_sums[key] += allocated_value
                allocated[key] = allocated_value

            net_unit_price = (
                allocated["subtotal_excluded"] / component["quantity"]
                if component["quantity"]
                else 0.0
            )
            if discount and discount_factor:
                price_unit = net_unit_price / discount_factor
            else:
                price_unit = net_unit_price
            unit_price_included = (
                allocated["line_total_included"] / component["quantity"]
                if component["quantity"]
                else 0.0
            )

            component["financials"] = {
                "price_unit": self.currency_id.round(price_unit),
                "discount": discount,
                "cgst_amount": allocated["cgst_amount"],
                "sgst_amount": allocated["sgst_amount"],
                "igst_amount": allocated["igst_amount"],
                "cgst_rate": tax_details["cgst_rate"],
                "sgst_rate": tax_details["sgst_rate"],
                "igst_rate": tax_details["igst_rate"],
                "tax_names": tax_names,
                "unit_price_included": self.currency_id.round(unit_price_included),
                "line_total_included": allocated["line_total_included"],
            }

        return components

    def _get_phantom_bom(self, product):
        """Find a Kit-type BoM for the given product."""
        if not product:
            return False
        return self.env['mrp.bom'].search([
            ('type', '=', 'phantom'),
            ('active', '=', True),
            '|',
            ('product_id', '=', product.id),
            ('product_tmpl_id', '=', product.product_tmpl_id.id),
        ], limit=1)

    def _get_kit_components(self, product):
        """Return a formatted string of BoM Kit components for the given product.
        Returns empty string if the product has no Kit-type BoM."""
        bom = self._get_phantom_bom(product)
        if not bom:
            return ""
        parts = []
        for bom_line in bom.bom_line_ids:
            comp_name = bom_line.product_id.name or ""
            qty = bom_line.product_qty
            uom = bom_line.product_uom_id.name or ""
            parts.append(f"{comp_name} ({qty:g} {uom})".strip())
        return ", ".join(parts)

    def _get_invoice_line_tax_details(self, line):
        self.ensure_one()
        quantity = line.quantity or 0.0
        discounted_unit_price = (line.price_unit or 0.0) * (1 - ((line.discount or 0.0) / 100.0))
        taxes_data = line.tax_ids.compute_all(
            discounted_unit_price,
            currency=self.currency_id,
            quantity=quantity,
            product=line.product_id,
            partner=self.partner_id,
            is_refund=self.move_type in ("out_refund", "in_refund"),
        )
        one_unit_tax_data = line.tax_ids.compute_all(
            discounted_unit_price,
            currency=self.currency_id,
            quantity=1.0,
            product=line.product_id,
            partner=self.partner_id,
            is_refund=self.move_type in ("out_refund", "in_refund"),
        )

        tax_totals = {
            "cgst_amount": 0.0,
            "sgst_amount": 0.0,
            "igst_amount": 0.0,
            "cgst_rate": 0.0,
            "sgst_rate": 0.0,
            "igst_rate": 0.0,
            "unit_price_included": one_unit_tax_data.get("total_included", 0.0),
            "line_total_included": taxes_data.get("total_included", 0.0),
        }

        for tax_line in taxes_data.get("taxes", []):
            tax = self.env["account.tax"].browse(tax_line.get("id"))
            matcher = "%s %s" % ((tax.name or "").upper(), (tax.tax_group_id.name or "").upper())
            amount = tax_line.get("amount", 0.0)
            rate = tax.amount if tax.amount_type == "percent" else 0.0

            if "IGST" in matcher:
                tax_totals["igst_amount"] += amount
                tax_totals["igst_rate"] += rate
            elif "CGST" in matcher:
                tax_totals["cgst_amount"] += amount
                tax_totals["cgst_rate"] += rate
            elif "SGST" in matcher or "UTGST" in matcher:
                tax_totals["sgst_amount"] += amount
                tax_totals["sgst_rate"] += rate

        return tax_totals

    @api.depends("bill_to_address", "bill_to_city", "bill_to_state_id", "bill_to_zip", "ship_to_address", "ship_to_city", "ship_to_state_id", "ship_to_zip")
    def _compute_legacy_address_text(self):
        for move in self:
            bill_state = move.bill_to_state_id.name if move.bill_to_state_id else False
            ship_state = move.ship_to_state_id.name if move.ship_to_state_id else False
            move.bill_to_address_text = "\n".join(
                [p for p in [move.bill_to_address, move.bill_to_city, bill_state, move.bill_to_zip] if p]
            ) or False
            move.ship_to_address_text = "\n".join(
                [p for p in [move.ship_to_address, move.ship_to_city, ship_state, move.ship_to_zip] if p]
            ) or False

    @api.depends(
        "bill_to_address",
        "bill_to_city",
        "bill_to_state_id",
        "bill_to_country",
        "bill_to_zip",
        "ship_to_address",
        "ship_to_city",
        "ship_to_state_id",
        "ship_to_country",
        "ship_to_zip",
    )
    def _compute_export_address_fields(self):
        for move in self:
            billing_partner = move.partner_id if move.bill_to_same_as_customer else move.billing_partner_id
            shipping_partner = move.partner_id if move.ship_to_same_as_customer else move.shipping_partner_id

            bill_state = move.bill_to_state_id.name or (billing_partner.state_id.name if billing_partner else False)
            bill_country = move.bill_to_country or (billing_partner.country_id.name if billing_partner else False)
            bill_zip = move.bill_to_zip or (billing_partner.zip if billing_partner else False)
            bill_address = "\n".join(
                [part for part in [move.bill_to_address, move.bill_to_city] if part]
            ) or (
                "\n".join([part for part in [billing_partner.street, billing_partner.street2, billing_partner.city] if part])
                if billing_partner
                else False
            )

            ship_state = move.ship_to_state_id.name or (shipping_partner.state_id.name if shipping_partner else False)
            ship_country = move.ship_to_country or (shipping_partner.country_id.name if shipping_partner else False)
            ship_zip = move.ship_to_zip or (shipping_partner.zip if shipping_partner else False)
            ship_address = "\n".join(
                [part for part in [move.ship_to_address, move.ship_to_city] if part]
            ) or (
                "\n".join([part for part in [shipping_partner.street, shipping_partner.street2, shipping_partner.city] if part])
                if shipping_partner
                else False
            )

            move.shipping_state = ship_state or False
            move.shipping_country = ship_country or False
            move.shipping_pincode = ship_zip or False
            move.shipping_address = ship_address or False
            move.billing_state = bill_state or False
            move.billing_country = bill_country or False
            move.billing_pincode = bill_zip or False
            move.billing_address = bill_address or False

    def _partner_address_vals(
        self,
        partner,
        prefix,
        partner_field=None,
        mobile_field=None,
        legacy_partner_field=None,
        name_field=None,
    ):
        vals = {
            f"{prefix}_address": False,
            f"{prefix}_city": False,
            f"{prefix}_state_id": False,
            f"{prefix}_country": False,
            f"{prefix}_zip": False,
        }
        if partner_field:
            vals[partner_field] = False
        if mobile_field:
            vals[mobile_field] = False
        if legacy_partner_field:
            vals[legacy_partner_field] = False
        if name_field:
            vals[name_field] = False

        if not partner:
            return vals

        address_lines = [line for line in (partner.street, partner.street2) if line]
        vals.update({
            f"{prefix}_address": "\n".join(address_lines) if address_lines else False,
            f"{prefix}_city": partner.city or False,
            f"{prefix}_state_id": partner.state_id.id or False,
            f"{prefix}_country": partner.country_id.name or False,
            f"{prefix}_zip": partner.zip or False,
        })
        if partner_field:
            vals[partner_field] = partner.id
        if mobile_field:
            vals[mobile_field] = partner.mobile or False
        if legacy_partner_field:
            vals[legacy_partner_field] = partner.id
        if name_field:
            vals[name_field] = partner.name or False
        return vals

    def _clear_partner_section_vals(self, prefix, partner_field, mobile_field, legacy_partner_field, name_field):
        return self._partner_address_vals(
            False,
            prefix,
            partner_field=partner_field,
            mobile_field=mobile_field,
            legacy_partner_field=legacy_partner_field,
            name_field=name_field,
        )

    def _get_delivery_type_default_vals(self):
        self.ensure_one()
        vals = {}

        if self.delivery_type == "direct_delivery":
            vals.update({
                "bill_to_same_as_customer": True,
                "ship_to_same_as_customer": True,
            })
            vals.update(
                self._partner_address_vals(
                    self.partner_id,
                    "bill_to",
                    partner_field="billing_partner_id",
                    mobile_field="billing_mobile",
                    legacy_partner_field="bill_to_partner_id",
                    name_field="billing_customer_name",
                )
            )
            vals.update(
                self._partner_address_vals(
                    self.partner_id,
                    "ship_to",
                    partner_field="shipping_partner_id",
                    mobile_field="shipping_mobile",
                    legacy_partner_field="ship_to_partner_id",
                    name_field="shipping_customer_name",
                )
            )
        elif self.delivery_type == "ship_to_different":
            vals.update({
                "bill_to_same_as_customer": True,
                "ship_to_same_as_customer": False,
            })
            vals.update(
                self._partner_address_vals(
                    self.partner_id,
                    "bill_to",
                    partner_field="billing_partner_id",
                    mobile_field="billing_mobile",
                    legacy_partner_field="bill_to_partner_id",
                    name_field="billing_customer_name",
                )
            )
            if self.shipping_partner_id and self.shipping_partner_id != self.partner_id:
                vals.update(
                    self._partner_address_vals(
                        self.shipping_partner_id,
                        "ship_to",
                        partner_field="shipping_partner_id",
                        mobile_field="shipping_mobile",
                        legacy_partner_field="ship_to_partner_id",
                        name_field="shipping_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "ship_to",
                        "shipping_partner_id",
                        "shipping_mobile",
                        "ship_to_partner_id",
                        "shipping_customer_name",
                    )
                )
        else:  # third_party_delivery
            vals.update({
                "bill_to_same_as_customer": False,
                "ship_to_same_as_customer": False,
            })
            if self.billing_partner_id and self.billing_partner_id != self.partner_id:
                vals.update(
                    self._partner_address_vals(
                        self.billing_partner_id,
                        "bill_to",
                        partner_field="billing_partner_id",
                        mobile_field="billing_mobile",
                        legacy_partner_field="bill_to_partner_id",
                        name_field="billing_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "bill_to",
                        "billing_partner_id",
                        "billing_mobile",
                        "bill_to_partner_id",
                        "billing_customer_name",
                    )
                )
            if self.shipping_partner_id and self.shipping_partner_id != self.partner_id:
                vals.update(
                    self._partner_address_vals(
                        self.shipping_partner_id,
                        "ship_to",
                        partner_field="shipping_partner_id",
                        mobile_field="shipping_mobile",
                        legacy_partner_field="ship_to_partner_id",
                        name_field="shipping_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "ship_to",
                        "shipping_partner_id",
                        "shipping_mobile",
                        "ship_to_partner_id",
                        "shipping_customer_name",
                    )
                )
        return vals

    def _apply_delivery_type_defaults(self):
        for move in self:
            move.update(move._get_delivery_type_default_vals())

    def _sync_invoice_address_partners(self):
        for move in self.filtered(lambda m: m.move_type in ("out_invoice", "out_refund")):
            updates = {}

            billing_partner = move.partner_id if move.bill_to_same_as_customer else move.billing_partner_id
            if billing_partner:
                updates.update(
                    move._partner_address_vals(
                        billing_partner,
                        "bill_to",
                        partner_field="billing_partner_id",
                        mobile_field="billing_mobile",
                        legacy_partner_field="bill_to_partner_id",
                    )
                )

            shipping_partner = move.partner_id if move.ship_to_same_as_customer else move.shipping_partner_id
            if shipping_partner:
                updates.update(
                    move._partner_address_vals(
                        shipping_partner,
                        "ship_to",
                        partner_field="shipping_partner_id",
                        mobile_field="shipping_mobile",
                        legacy_partner_field="ship_to_partner_id",
                    )
                )

            if updates:
                super(AccountMove, move).write(updates)

    @api.onchange('partner_id')
    def _onchange_partner_set_fiscal_position(self):
        if self.partner_id:
            self._apply_delivery_type_defaults()

        if not self.partner_id or not self.company_id:
            return

        company_state = self.company_id.state_id
        partner_state = self.partner_id.state_id

        if not company_state or not partner_state:
            return

        FiscalPosition = self.env['account.fiscal.position']

        # Intra-state (same state)
        if company_state.id == partner_state.id:
            fiscal_position = FiscalPosition.search([
                ('name', '=', 'GST Intra State'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        else:
            # Inter-state (different state)
            fiscal_position = FiscalPosition.search([
                ('name', '=', 'GST Inter State'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)

        if fiscal_position:
            self.fiscal_position_id = fiscal_position

    @api.onchange("move_type", "company_id")
    def _onchange_apply_default_cash_rounding(self):
        self._apply_default_cash_rounding()

    @api.onchange("bill_to_same_as_customer")
    def _onchange_bill_to_same_as_customer(self):
        if self.bill_to_same_as_customer:
            self.update(
                self._partner_address_vals(
                    self.partner_id,
                    "bill_to",
                    partner_field="billing_partner_id",
                    mobile_field="billing_mobile",
                    legacy_partner_field="bill_to_partner_id",
                    name_field="billing_customer_name",
                )
            )
        elif self.delivery_type == "direct_delivery":
            self.bill_to_same_as_customer = True

    @api.onchange("billing_partner_id")
    def _onchange_billing_partner_id(self):
        if not self.bill_to_same_as_customer:
            self.update(
                self._partner_address_vals(
                    self.billing_partner_id,
                    "bill_to",
                    partner_field="billing_partner_id",
                    mobile_field="billing_mobile",
                    legacy_partner_field="bill_to_partner_id",
                    name_field="billing_customer_name",
                )
            )

    @api.onchange("ship_to_same_as_customer")
    def _onchange_ship_to_same_as_customer(self):
        if self.ship_to_same_as_customer:
            self.update(
                self._partner_address_vals(
                    self.partner_id,
                    "ship_to",
                    partner_field="shipping_partner_id",
                    mobile_field="shipping_mobile",
                    legacy_partner_field="ship_to_partner_id",
                    name_field="shipping_customer_name",
                )
            )
        elif self.delivery_type == "direct_delivery":
            self.ship_to_same_as_customer = True

    @api.onchange("shipping_partner_id")
    def _onchange_shipping_partner_id(self):
        if not self.ship_to_same_as_customer:
            self.update(
                self._partner_address_vals(
                    self.shipping_partner_id,
                    "ship_to",
                    partner_field="shipping_partner_id",
                    mobile_field="shipping_mobile",
                    legacy_partner_field="ship_to_partner_id",
                    name_field="shipping_customer_name",
                )
            )

    @api.onchange("delivery_type")
    def _onchange_delivery_type(self):
        self._apply_delivery_type_defaults()

    @api.model_create_multi
    def create(self, vals_list):
        today = fields.Date.context_today(self)
        for vals in vals_list:
            move_type = vals.get("move_type") or self.env.context.get("default_move_type")
            state = vals.get("state", "draft")
            if (
                move_type in ("out_invoice", "out_refund")
                and state == "draft"
                and not vals.get("invoice_date")
            ):
                vals["invoice_date"] = today
        moves = super().create(vals_list)
        explicit_delivery_vals_by_move = {}
        for move, create_vals in zip(moves, vals_list):
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
            has_explicit_delivery_vals = self._has_explicit_delivery_address_vals(create_vals)
            explicit_delivery_vals_by_move[move.id] = has_explicit_delivery_vals
            if has_explicit_delivery_vals:
                continue
            super(AccountMove, move).write(move._get_delivery_type_default_vals())
        moves._apply_default_cash_rounding()
        moves.filtered(
            lambda m: m.move_type in ("out_invoice", "out_refund")
            and not explicit_delivery_vals_by_move.get(m.id)
        )._sync_invoice_address_partners()
        return moves

    def write(self, vals):
        result = super().write(vals)
        relevant_fields = {
            "partner_id",
            "delivery_type",
            "bill_to_same_as_customer",
            "ship_to_same_as_customer",
            "billing_partner_id",
            "shipping_partner_id",
        }
        if relevant_fields & set(vals) and not self.env.context.get("skip_delivery_defaults"):
            for move in self.filtered(lambda m: m.move_type in ("out_invoice", "out_refund")):
                super(AccountMove, move.with_context(skip_delivery_defaults=True)).write(
                    move._get_delivery_type_default_vals()
                )
            self._sync_invoice_address_partners()
        return result

    def _dw_get_hsn_summary_table(self):
        self.ensure_one()

        display_uom = self.env.user.user_has_groups("uom.group_uom")
        default_summary = self._l10n_in_get_hsn_summary_table()
        summary_map = OrderedDict()
        has_gst = False
        has_igst = False

        invoice_lines = self.invoice_line_ids.filtered(
            lambda line: not line.display_type and (line.hsn_code or (line.product_id and line.product_id.l10n_in_hsn_code))
        )
        if not invoice_lines:
            invoice_lines = self.line_ids.filtered(
                lambda line: not line.display_type
                and not line.tax_line_id
                and line.product_id
                and (line.hsn_code or (line.product_id and line.product_id.l10n_in_hsn_code))
            )

        for line in invoice_lines:
            hsn_code = line.hsn_code or (line.product_id and line.product_id.l10n_in_hsn_code) or ""
            quantity = line.quantity or 0.0
            taxable_value = line.price_subtotal or 0.0

            rate = 0.0
            cgst_amount = 0.0
            sgst_amount = 0.0
            igst_amount = 0.0

            for tax in line.tax_ids:
                tax_amount = tax.amount or 0.0
                tax_name = (tax.name or "").upper()
                tax_group_name = (tax.tax_group_id.name or "").upper()
                matcher = f"{tax_name} {tax_group_name}"

                if "IGST" in matcher:
                    igst_amount += taxable_value * tax_amount / 100.0
                    rate += tax_amount
                    has_igst = True
                elif "CGST" in matcher:
                    cgst_amount += taxable_value * tax_amount / 100.0
                    rate += tax_amount
                    has_gst = True
                elif "SGST" in matcher or "UTGST" in matcher:
                    sgst_amount += taxable_value * tax_amount / 100.0
                    rate += tax_amount
                    has_gst = True

            item = summary_map.setdefault(hsn_code, {
                "l10n_in_hsn_code": hsn_code,
                "quantity": 0.0,
                "uom": line.product_uom_id,
                "rate": 0.0,
                "amount_untaxed": 0.0,
                "tax_amount_sgst": 0.0,
                "tax_amount_cgst": 0.0,
                "tax_amount_igst": 0.0,
            })

            item["quantity"] += quantity
            item["amount_untaxed"] += taxable_value
            item["tax_amount_sgst"] += sgst_amount
            item["tax_amount_cgst"] += cgst_amount
            item["tax_amount_igst"] += igst_amount
            item["rate"] = rate

        if not summary_map:
            return default_summary

        default_items_by_hsn = {
            item.get("l10n_in_hsn_code"): dict(item)
            for item in (default_summary or {}).get("items", [])
            if item.get("l10n_in_hsn_code")
        }
        merged_items = []
        seen_hsn_codes = set()

        for hsn_code, values in summary_map.items():
            merged_item = default_items_by_hsn.get(hsn_code, {}).copy()
            merged_item.update(values)
            merged_items.append(merged_item)
            seen_hsn_codes.add(hsn_code)

        for hsn_code, item in default_items_by_hsn.items():
            if hsn_code not in seen_hsn_codes:
                merged_items.append(item)
                if item.get("tax_amount_sgst") or item.get("tax_amount_cgst"):
                    has_gst = True
                if item.get("tax_amount_igst"):
                    has_igst = True

        nb_columns = 4
        if has_gst:
            nb_columns += 2
        if has_igst:
            nb_columns += 1

        return {
            "has_gst": has_gst,
            "has_igst": has_igst,
            "has_cess": (default_summary or {}).get("has_cess", False),
            "nb_columns": nb_columns,
            "display_uom": display_uom,
            "items": merged_items,
        }

    def action_post(self):
        """Preserve the existing invoice number when re-posting an out_invoice.

        First post  -> name is '/' -> Odoo assigns the next sequence normally.
        Re-post     -> name already set (e.g. 'TEST0019') -> lock it, prevent
                       _set_next_sequence() from replacing it, and use a direct
                       SQL restore as an absolute final safety-net.
        """
        # ── Step 1: Snapshot names of already-numbered customer invoices ──────
        locked_names = {
            move.id: move.name
            for move in self.filtered(lambda m: m.move_type == 'out_invoice')
            if move.posted_before and move.name and move.name != '/'
        }

        # ── Step 2: Standard posting with locked names in context ─────────────
        # _set_next_sequence override intercepts and restores name for locked
        # moves instead of generating a new sequence number.
        res = super(AccountMove, self.with_context(
            dw_locked_invoice_names=locked_names
        )).action_post()

        # ── Step 3: Absolute safety-net via direct SQL UPDATE ─────────────────
        # If _compute_name / _set_next_sequence still changed the name (for any
        # reason), we forcefully restore it using a raw SQL UPDATE that bypasses
        # ALL ORM validation, compute triggers, and constraints.
        moves_to_fix = [
            (original, move_id)
            for move_id, original in locked_names.items()
            if self.browse(move_id).name != original
        ]
        if moves_to_fix:
            for original, move_id in moves_to_fix:
                self.env.cr.execute(
                    "UPDATE account_move SET name = %s WHERE id = %s",
                    (original, move_id)
                )
                # Invalidate ORM cache so UI shows the corrected name.
                self.browse(move_id).invalidate_recordset(['name'])

        # ── Step 4: Activity timeline entries ─────────────────────────────────
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            sale_orders = move.invoice_line_ids.sale_line_ids.order_id
            for order in sale_orders:
                self.env['activity.timeline'].create({
                    'quotation_id': order.id,
                    'activity_type': 'invoice',
                    'description': 'Invoice %s posted.' % move.name,
                    'status': 'Posted',
                })
        return res

    # =========================================================================
    # Invoice Number Preservation
    # =========================================================================
    # Strategy overview:
    #
    # A. _set_next_sequence  (PRIMARY guard for re-post)
    #    Core calls move._set_next_sequence() inside _compute_name when it
    #    decides to mint a new number.  We override it to short-circuit that
    #    for moves whose id is in 'dw_locked_invoice_names' context.  This
    #    avoids all ORM cache-timing issues because we never read move.name
    #    during a compute of name itself.
    #
    # B. _compute_name override  (guard for draft/cancel states)
    #    When state -> draft or cancel, the standard logic can clear name to
    #    '/' for cross-period sequences.  We exclude already-named,
    #    previously-posted out_invoices from that path.
    #
    # C. button_draft / button_cancel  (snapshot + restore safety-net)
    # =========================================================================

    def _set_next_sequence(self):
        """PRIMARY guard for re-post: skip sequence generation when the move
        name is locked in context.

        action_post() passes 'dw_locked_invoice_names' in context.  When
        _compute_name calls self._set_next_sequence() on a locked move we
        restore the original name instead of generating a new one.
        """
        locked = self.env.context.get('dw_locked_invoice_names', {})
        if self.move_type == 'out_invoice' and self.id in locked:
            original = locked[self.id]
            if original and original != '/':
                self.name = original
                return
        return super()._set_next_sequence()

    def _dw_posted_name_map(self):
        """Return {move_id: name} for out_invoice moves with a real name."""
        return {
            move.id: move.name
            for move in self
            if move.move_type == 'out_invoice'
            and move.posted_before
            and move.name
            and move.name != '/'
        }

    def _dw_restore_names(self, name_map):
        """Write back preserved names if _compute_name wiped them."""
        for move in self:
            preserved = name_map.get(move.id)
            if preserved and (not move.name or move.name == '/'):
                super(AccountMove, move).write({'name': preserved})

    def button_draft(self):
        """Reset to draft while preserving invoice number for out_invoices."""
        name_map = self._dw_posted_name_map()
        result = super().button_draft()
        self._dw_restore_names(name_map)
        return result

    def button_cancel(self):
        """Cancel while preserving invoice number for out_invoices."""
        name_map = self._dw_posted_name_map()
        result = super().button_cancel()
        self._dw_restore_names(name_map)
        return result

    @api.depends('posted_before', 'state', 'journal_id', 'date', 'move_type', 'payment_id')
    def _compute_name(self):
        """Guard draft/cancel: prevent name being cleared to '/' for out_invoice
        moves that were previously posted.

        In draft/cancel the name field is NOT the one being recomputed so
        reading move.name here is safe (returns the stored DB value).

        The re-post scenario (state->posted) is handled by _set_next_sequence.
        """
        protected = self.filtered(
            lambda m: (
                m.move_type == 'out_invoice'
                and m.posted_before
                and m.name
                and m.name != '/'
                and m.state in ('draft', 'cancel')
            )
        )
        remaining = self - protected
        if remaining:
            super(AccountMove, remaining)._compute_name()
        # Safety net: restore if ORM cache flush wiped the name.
        for move in protected:
            if not move.name or move.name == '/':
                original = move._origin.name
                if original and original != '/':
                    super(AccountMove, move).write({'name': original})


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    hsn_code = fields.Char(
        string="HSN",
        related="product_id.l10n_in_hsn_code",
        store=True,
    )

    # ─── XLSX Import GST amounts (editable, informational) ─────────
    product_sku = fields.Char(
        string="SKU",
        related="product_id.default_code",
        store=True,
    )
    dw_cgst_amount = fields.Float(string="CGST Amount", digits=(16, 2), copy=False)
    dw_sgst_amount = fields.Float(string="SGST Amount", digits=(16, 2), copy=False)
    dw_igst_amount = fields.Float(string="IGST Amount", digits=(16, 2), copy=False)
    dw_taxable_value = fields.Float(string="Taxable Value", digits=(16, 2), copy=False)
    dw_total_tax_amount = fields.Float(string="Total Tax Amount", digits=(16, 2), copy=False)
    dw_line_total_imported = fields.Float(string="Imported Line Total", digits=(16, 2), copy=False)
