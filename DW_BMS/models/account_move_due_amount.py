from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = "account.move"

    customer_due_amount = fields.Monetary(
        string="Customer Total Due",
        compute="_compute_customer_due_amount",
        currency_field="currency_id",
        store=False,
    )

    @api.depends("partner_id")
    def _compute_customer_due_amount(self):
        for move in self:
            move.customer_due_amount = 0.0

        partner_ids = self.mapped("partner_id").ids
        if not partner_ids:
            return

        domain = [
            ("partner_id", "in", partner_ids),
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("move_type", "=", "out_invoice"),
        ]

        grouped_data = self.env["account.move"].read_group(
            domain,
            ["partner_id", "amount_residual:sum"],
            ["partner_id"]
        )

        due_amounts = {
            group["partner_id"][0]: group["amount_residual"]
            for group in grouped_data
            if group.get("partner_id")
        }

        for move in self:
            if move.partner_id:
                move.customer_due_amount = due_amounts.get(move.partner_id.id, 0.0)

    previous_due_invoices_details = fields.Html(
        string="Previous Pending Invoices",
        compute="_compute_previous_due_invoices_details",
        store=False,
    )

    @api.depends("partner_id")
    def _compute_previous_due_invoices_details(self):
        for move in self:
            move.previous_due_invoices_details = False

        partner_ids = self.mapped("partner_id").ids
        if not partner_ids:
            return

        domain = [
            ("partner_id", "in", partner_ids),
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial"]),
            ("move_type", "=", "out_invoice"),
        ]

        invoices_data = self.env["account.move"].search_read(
            domain,
            ["partner_id", "name", "amount_residual", "currency_id"]
        )

        partner_invoice_map = {}
        for inv in invoices_data:
            pid = inv["partner_id"][0]
            if pid not in partner_invoice_map:
                partner_invoice_map[pid] = []
            partner_invoice_map[pid].append(inv)

        for move in self:
            if move.partner_id and move.partner_id.id in partner_invoice_map:
                invs = partner_invoice_map[move.partner_id.id]
                lines = []
                total_previous_due = 0.0
                currency_symbol = ""
                for inv in invs:
                    if move._origin and inv["id"] == move._origin.id:
                        continue
                    
                    currency_id = inv.get("currency_id")
                    if currency_id:
                        currency = self.env["res.currency"].browse(currency_id[0])
                        symbol = currency.symbol or ""
                    else:
                        symbol = move.currency_id.symbol or ""
                        
                    currency_symbol = symbol
                    amount = inv["amount_residual"]
                    total_previous_due += amount
                    lines.append(f"<li><b>{inv['name']}</b>: {symbol}{amount:,.2f}</li>")
                
                if lines:
                    lines.append(f"<li style='list-style-type: none; border-top: 1px solid #ffaaaa; margin-top: 5px; padding-top: 5px; font-weight: bold;'>Total Due: {currency_symbol}{total_previous_due:,.2f}</li>")
                    move.previous_due_invoices_details = f"<div style='margin-top: 5px; padding: 10px; background-color: #fff3f3; border-left: 3px solid #ff4d4d; border-radius: 4px;'><strong style='color: #cc0000; margin-bottom: 5px; display: block;'>Previous Unpaid Invoices:</strong><ul style='margin-bottom:0; padding-left:20px; color:#cc0000;'>{''.join(lines)}</ul></div>"
