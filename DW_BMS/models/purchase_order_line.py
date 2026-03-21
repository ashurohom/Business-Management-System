from odoo import api, fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    def _is_bms_purchase_user(self):
        return self.env.user.has_group("DW_BMS.group_bms_purchase")

    def _compute_tax_id(self):
        super()._compute_tax_id()
        if not self._is_bms_purchase_user():
            return

        for line in self:
            if not line.product_id or line.display_type:
                continue
            line.taxes_id = line.product_id.sudo().supplier_taxes_id._filter_taxes_by_company(line.company_id)

    @api.onchange("product_id", "product_qty", "product_uom")
    def _onchange_dw_force_product_defaults(self):
        for line in self:
            if not line.product_id or line.display_type:
                continue

            order = line.order_id
            product = line.product_id.sudo()
            company = order.company_id or self.env.company
            currency = order.currency_id or company.currency_id
            order_date = order.date_order or fields.Date.today()

            taxes = product.supplier_taxes_id.filtered(
                lambda tax: not tax.company_id or tax.company_id == company
            )
            if taxes:
                line.taxes_id = taxes

            seller = product._select_seller(
                partner_id=order.partner_id,
                quantity=line.product_qty,
                date=order_date,
                uom_id=line.product_uom,
                params={"order_id": order},
            )

            if seller:
                price = seller.price
                if seller.currency_id and seller.currency_id != currency:
                    price = seller.currency_id._convert(price, currency, company, order_date, round=False)
                if seller.product_uom and line.product_uom and seller.product_uom != line.product_uom:
                    price = seller.product_uom._compute_price(price, line.product_uom)
                line.price_unit = price
            elif not line.price_unit:
                line.price_unit = product.standard_price or 0.0

    @api.depends("product_qty", "product_uom", "company_id")
    def _compute_price_unit_and_date_planned_and_name(self):
        super()._compute_price_unit_and_date_planned_and_name()
        if not self._is_bms_purchase_user():
            return

        for line in self:
            if not line.product_id or line.invoice_lines or not line.company_id or line.display_type:
                continue

            order = line.order_id
            product = line.product_id.sudo()
            company = line.company_id
            currency = line.currency_id or company.currency_id
            order_date = order.date_order or fields.Date.context_today(line)
            date_for_seller = order.date_order.date() if order.date_order else fields.Date.context_today(line)

            seller = product._select_seller(
                partner_id=order.partner_id,
                quantity=line.product_qty,
                date=date_for_seller,
                uom_id=line.product_uom,
                params={"order_id": order},
            )

            if seller:
                price = seller.price
                if seller.currency_id and seller.currency_id != currency:
                    price = seller.currency_id._convert(price, currency, company, order_date, round=False)
                if seller.product_uom and line.product_uom and seller.product_uom != line.product_uom:
                    price = seller.product_uom._compute_price(price, line.product_uom)
                line.price_unit = price
            else:
                line.price_unit = product.standard_price or 0.0
