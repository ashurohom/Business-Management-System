from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    _INVOICE_TYPE_SEQUENCE_MAP = {
        'flipkart_wb': 'invoice.flipkart.wb',
        'vastu_delhi': 'invoice.vc.delhi',
        'daily_sales': 'invoice.daily.sales',
        'flipkart_mh': 'invoice.flipkart.mh',
        'kv_hr': 'invoice.kv.hr',
        'website_sales': 'invoice.website.sales',
        'export_sales': 'invoice.export.sales',
        'kv_tn': 'invoice.kv.tn',
        'kv_ka': 'invoice.kv.ka',
        'kv_mh': 'invoice.kv.mh',
        'kv_wb': 'invoice.kv.wb',
        'kv_tel': 'invoice.kv.tel',
        'test': 'invoice.test',
    }

    invoice_type = fields.Selection([
        ('flipkart_wb', 'Flipkart WB'),
        ('vastu_delhi', 'Vastu Craft (Delhi)'),
        ('daily_sales', 'Daily Sales'),
        ('flipkart_mh', 'Flipkart MH'),
        ('kv_hr', 'KV Enterprises (Haryana)'),
        ('website_sales', 'Website Sales'),
        ('export_sales', 'Export Sales'),
        ('kv_tn', 'KV Enterprises (Tamil Nadu)'),
        ('kv_ka', 'KV Enterprises (Karnataka)'),
        ('kv_mh', 'KV Enterprises (Maharashtra)'),
        ('kv_wb', 'KV Enterprises (West Bengal)'),
        ('kv_tel', 'KV Enterprises (Telangana)'),
        ('test', 'Test'),
    ], string="Invoice Type", default='daily_sales', copy=False)

    def _skip_invoice_type_sequence(self):
        return bool(self.env.context.get('skip_invoice_type_sequence'))

    def _uses_custom_invoice_type_sequence(self):
        self.ensure_one()
        return self.move_type == 'out_invoice' and bool(self.invoice_type) and not self._skip_invoice_type_sequence()

    def _get_invoice_type_sequence_code(self):
        self.ensure_one()
        return self._INVOICE_TYPE_SEQUENCE_MAP.get(self.invoice_type)

    def _get_next_unique_invoice_type_number(self, seq_code):
        self.ensure_one()

        Move = self.env['account.move'].sudo()
        attempts = 0
        while attempts < 50:
            next_number = self.env['ir.sequence'].next_by_code(seq_code)
            if not next_number:
                break

            duplicate = Move.search([
                ('id', '!=', self.id),
                ('company_id', '=', self.company_id.id),
                ('name', '=', next_number),
            ], limit=1)
            if not duplicate:
                return next_number
            attempts += 1

        raise UserError(
            f"Unable to generate a unique invoice number for sequence '{seq_code}'. "
            "Please check the sequence next number."
        )

    def _assign_invoice_type_sequence(self):
        if self._skip_invoice_type_sequence():
            return

        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            if not move.invoice_type:
                raise UserError("Please select Invoice Type before posting invoice.")

            seq_code = move._get_invoice_type_sequence_code()
            if not seq_code:
                raise UserError("No sequence mapping found for the selected Invoice Type.")

            next_number = move._get_next_unique_invoice_type_number(seq_code)
            move.write({'name': next_number})

    def _assign_invoice_type_sequence_validation(self):
        if self._skip_invoice_type_sequence():
            return

        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            if not move.invoice_type:
                raise UserError("Please select Invoice Type before posting invoice.")

            seq_code = move._get_invoice_type_sequence_code()
            if not seq_code:
                raise UserError("No sequence mapping found for the selected Invoice Type.")

            sequence = self.env['ir.sequence'].sudo().search([('code', '=', seq_code)], limit=1)
            if not sequence:
                raise UserError(f"No sequence is configured for code '{seq_code}'.")

    @api.depends('posted_before', 'state', 'journal_id', 'date', 'move_type', 'payment_id', 'invoice_type')
    def _compute_name(self):
        custom_moves = self.filtered(lambda m: m._uses_custom_invoice_type_sequence())
        regular_moves = self - custom_moves

        if regular_moves:
            super(AccountMove, regular_moves)._compute_name()

        for move in custom_moves:
            if move.state == 'draft':
                move.name = '/'
            elif not move.name:
                move.name = '/'

        if custom_moves:
            custom_moves._inverse_name()

    def action_post(self):
        self._assign_invoice_type_sequence_validation()
        result = super().action_post()
        self.filtered(lambda m: m.state == 'posted')._assign_invoice_type_sequence()
        return result
