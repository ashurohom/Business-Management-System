from odoo import _, models


class SaleOrderDiscount(models.TransientModel):
    _inherit = "sale.order.discount"

    def _get_discount_product(self):
        self.ensure_one()

        discount_product = self.company_id.sale_discount_product_id
        if discount_product:
            return discount_product

        discount_values = self._prepare_discount_product_values()
        company = self.company_id.sudo()
        product_model = self.env["product.product"].with_context(active_test=False).sudo()
        product_name = discount_values.get("name") or _("Discount")

        reusable_product = product_model.search(
            [
                ("name", "=ilike", product_name),
                ("type", "=", discount_values.get("type", "service")),
                ("invoice_policy", "=", discount_values.get("invoice_policy", "order")),
                ("company_id", "in", [company.id, False]),
            ],
            order="company_id desc, active desc, id desc",
            limit=1,
        )
        if reusable_product:
            if not reusable_product.active:
                reusable_product.active = True
            company.sale_discount_product_id = reusable_product
            return reusable_product

        discount_product = product_model.with_context(
            skip_duplicate_product_name_check=True
        ).create(discount_values)
        company.sale_discount_product_id = discount_product
        return discount_product
