from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    price_incl_tax = fields.Float(
        string="Rate Incl Tax",
        digits="Product Price",
    )

    min_sale_price = fields.Float(
        string="Minimum Sale Price",
        related="product_id.product_tmpl_id.min_sale_price",
        readonly=True,
        store=False,
    )

    stock_qty = fields.Float(
        string="Stock",
        compute="_compute_stock_qty",
        store=False,
    )

    @api.depends("product_id")
    def _compute_stock_qty(self):
        for line in self:
            if line.product_id:
                line.stock_qty = line.product_id.with_context(
                    warehouse=line.order_id.warehouse_id.id
                ).qty_available
            else:
                line.stock_qty = 0.0

    def _get_price_incl_from_unit(self, unit_price):
        self.ensure_one()
        currency = self.order_id.currency_id or self.env.company.currency_id
        taxes_res = self.tax_id.compute_all(
            unit_price,
            currency=currency,
            quantity=1.0,
            product=self.product_id,
            partner=self.order_id.partner_id,
        )
        return taxes_res.get("total_included", unit_price)

    def _get_unit_from_price_incl(self, price_incl):
        self.ensure_one()
        currency = self.order_id.currency_id or self.env.company.currency_id
        rounding = currency.rounding or 0.01

        if not self.tax_id:
            return price_incl

        # Invert tax compute using numeric solve so it works with multiple taxes.
        low = 0.0
        high = max(price_incl * 2.0, 1.0)
        for _ in range(10):
            total_high = self._get_price_incl_from_unit(high)
            if total_high >= price_incl:
                break
            high *= 2.0

        for _ in range(40):
            mid = (low + high) / 2.0
            total_mid = self._get_price_incl_from_unit(mid)
            if float_is_zero(total_mid - price_incl, precision_rounding=rounding):
                return mid
            if total_mid < price_incl:
                low = mid
            else:
                high = mid
        return (low + high) / 2.0

    @api.onchange("price_unit", "tax_id")
    def _onchange_price_unit_tax_set_price_incl_tax(self):
        for line in self:
            if line.display_type:
                continue
            line.price_incl_tax = line._get_price_incl_from_unit(line.price_unit or 0.0)

    @api.onchange("price_incl_tax")
    def _onchange_price_incl_tax_set_price_unit(self):
        for line in self:
            if line.display_type:
                continue
            line.price_unit = line._get_unit_from_price_incl(line.price_incl_tax or 0.0)

    @api.constrains("price_incl_tax", "product_id")
    def _check_price_incl_tax_not_below_min_sale_price(self):
        for line in self:
            if not line.product_id or line.display_type:
                continue

            min_allowed_price = line.product_id.product_tmpl_id.min_sale_price or 0.0
            rounding = line.order_id.currency_id.rounding or 0.01

            if float_compare(line.price_incl_tax or 0.0, min_allowed_price, precision_rounding=rounding) < 0:
                raise ValidationError(
                    "Rate Incl Tax cannot be less than the minimum allowed selling price.\n"
                    "Product: %s\n"
                    "Minimum allowed price: %.2f\n"
                    "Entered Rate Incl Tax: %.2f"
                    % (
                        line.product_id.display_name,
                        min_allowed_price,
                        line.price_incl_tax or 0.0,
                    )
                )

    @api.constrains("product_uom_qty", "product_id", "order_id", "order_id.warehouse_id")
    def _check_order_qty_not_more_than_stock(self):
        if self.env.context.get("skip_stock_validation"):
            return

        for line in self:
            if not line.product_id or line.display_type:
                continue

            available_qty = line.product_id.with_context(
                warehouse=line.order_id.warehouse_id.id
            ).qty_available
            rounding = line.product_uom.rounding or line.product_id.uom_id.rounding or 0.01

            if float_compare(line.product_uom_qty or 0.0, available_qty, precision_rounding=rounding) > 0:
                raise ValidationError(
                    "Ordered quantity cannot be more than available stock.\n"
                    "Product: %s\n"
                    "Available stock: %.2f\n"
                    "Entered quantity: %.2f"
                    % (
                        line.product_id.display_name,
                        available_qty,
                        line.product_uom_qty or 0.0,
                    )
                )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    total_products_weight = fields.Float(
        string="Total Products Weight",
        compute="_compute_total_products_weight",
        store=True,
    )

    @api.depends("order_line.product_id.weight", "order_line.product_uom_qty", "order_line.display_type")
    def _compute_total_products_weight(self):
        for order in self:
            order.total_products_weight = sum(
                (line.product_id.weight or 0.0) * line.product_uom_qty
                for line in order.order_line
                if not line.display_type
            )

    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["invoice_date"] = fields.Date.context_today(self)
        return vals

    def action_open_packing_order(self):
        self.ensure_one()
        invoice = self.env["account.move"].search(
            [
                ("move_type", "=", "out_invoice"),
                ("invoice_origin", "=", self.name),
            ],
            order="id desc",
            limit=1,
        )
        if not invoice:
            raise UserError("Create the customer invoice first, then open Packing from the invoice.")
        return invoice.action_open_packing_order()
