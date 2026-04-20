import math

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    roundup_total = fields.Monetary(
        string="Roundup Total",
        compute="_compute_roundup_total",
        currency_field="currency_id",
    )

    @api.depends("amount_total")
    def _compute_roundup_total(self):
        for order in self:
            order.roundup_total = order._get_rounded_total_amount()

    def _get_rounded_total_amount(self):
        self.ensure_one()
        amount_total = self.amount_total or 0.0
        if amount_total >= 0:
            base_amount = math.floor(amount_total)
            fractional_amount = amount_total - base_amount
            return base_amount + (1 if fractional_amount >= 0.5 else 0)

        absolute_total = abs(amount_total)
        base_amount = math.floor(absolute_total)
        fractional_amount = absolute_total - base_amount
        rounded_total = base_amount + (1 if fractional_amount >= 0.5 else 0)
        return -rounded_total

    @api.onchange(
        "order_line",
        "order_line.product_qty",
        "order_line.price_unit",
        "order_line.discount",
        "order_line.taxes_id",
    )
    def _onchange_roundup_total(self):
        for order in self:
            order.roundup_total = order._get_rounded_total_amount()
