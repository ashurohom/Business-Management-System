from odoo import models, fields
from odoo.exceptions import UserError
import base64, io
import openpyxl


class InvoiceImportWizard(models.TransientModel):
    _name = 'dw.invoice.import.v2.wizard'
    _description = 'DW SKU Invoice Import Wizard'

    file = fields.Binary(required=True)
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    invoice_date = fields.Date(required=True)
    shipping_id = fields.Char(string='Shipping Id')
    invoice_type = fields.Selection(
        selection=lambda self: self.env['account.move']._fields['invoice_type'].selection,
        required=True
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')
    ], default='draft')

    def action_import(self):
        if not self.file:
            raise UserError("Please upload file.")

        data = base64.b64decode(self.file)
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        sheet = wb.active

        alias_model = self.env['dw.product.name.alias']
        product_model = self.env['product.product']

        # 🔥 FAST lookup
        alias_map = {
            a.name.strip().lower(): a.product_tmpl_id.product_variant_id.id
            for a in alias_model.search([])
        }

        product_qty = {}
        errors = []

        for idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            sku = row[0] if len(row) > 0 else False
            qty = row[1] if len(row) > 1 else False
            name = row[2] if len(row) > 2 else False

            if not sku or not qty:
                continue

            key = str(sku).strip().lower()
            product_id = alias_map.get(key)

            if not product_id:
                sku_text = str(sku).strip()
                product = product_model.search([('name', '=ilike', sku_text)], limit=1)
                if not product:
                    product = product_model.search([('name', 'ilike', sku_text)], limit=1)
                product_id = product.id if product else False

            if not product_id and name:
                product = product_model.search([('name', 'ilike', name)], limit=1)
                product_id = product.id if product else False

            if not product_id:
                errors.append(f"Row {idx}: SKU/Product not found → {sku}")
                continue

            product_qty[product_id] = product_qty.get(product_id, 0) + qty

        # ❌ STOP if error
        if errors:
            raise UserError("\n".join(errors[:5]))

        # 🔥 Sequence based on invoice_type
        seq_code = f"dw.invoice.{self.invoice_type}"
        seq = self.env['ir.sequence'].search([('code', '=', seq_code)], limit=1)

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.invoice_date,
            'invoice_type': self.invoice_type,
            'dw_shipping_id': self.shipping_id,
        }

        if seq:
            invoice_vals['name'] = seq.next_by_id()

        invoice = self.env['account.move'].create(invoice_vals)

        lines = []
        for pid, qty in product_qty.items():
            p = product_model.browse(pid)
            lines.append((0, 0, {
                'product_id': p.id,
                'quantity': qty,
                'price_unit': p.lst_price,
                'tax_ids': [(6, 0, p.taxes_id.ids)]
            }))

        invoice.write({'invoice_line_ids': lines})
        invoice.action_post()

        self.state = 'done'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Invoice Created',
                'message': f"Invoice {invoice.name} created successfully.",
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
