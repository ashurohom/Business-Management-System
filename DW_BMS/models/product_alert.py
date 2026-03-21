from odoo import api, fields, models, _


class ProductTemplate(models.Model):
    _inherit = "product.template"

    min_alert_qty = fields.Float(
        string="Minimum Order Quantity",
        default=5.0,
        help="If On Hand Quantity goes below this value, product will be marked as Low Stock.",
    )


class ProductProduct(models.Model):
    _inherit = "product.product"
    _order = "purchase_status_sequence asc, id desc"

    sku = fields.Char(
        related="product_tmpl_id.sku",
        string="SKU",
        readonly=True,
        store=True,
    )

    min_alert_qty = fields.Float(
        related="product_tmpl_id.min_alert_qty",
        readonly=False,
    )

    alert_status = fields.Selection(
        [
            ("normal", "Normal"),
            ("low", "Low Stock"),
        ],
        string="Alert Status",
        compute="_compute_alert_status",
    )

    is_low_stock = fields.Boolean(
        string="Low Stock",
        compute="_compute_alert_status",
        search="_search_low_stock",
    )

    purchase_status = fields.Selection(
        selection=[
            ("no_order", "Not Ordered"),
            ("ordered", "Ordered"),
            ("stock_received", "Stock Received"),
        ],
        string="Purchase Status",
        default="no_order",
        help="Manual purchase status. Use the button in the list to cycle between states.",
    )
    purchase_status_sequence = fields.Integer(
        string="Purchase Status Sequence",
        compute="_compute_purchase_status_sequence",
        store=True,
        index=True,
    )

    purchase_vendor_id = fields.Many2one(
        comodel_name="res.partner",
        string="Vendor",
        help="Vendor associated with this product's purchase.",
    )

    purchase_order_date = fields.Date(
        string="Order Date",
        help="Date when the product was marked as ordered.",
    )

    @api.depends("purchase_status")
    def _compute_purchase_status_sequence(self):
        status_sequence_map = {
            "no_order": 1,
            "ordered": 2,
            "stock_received": 3,
        }
        for product in self:
            product.purchase_status_sequence = status_sequence_map.get(
                product.purchase_status or "no_order",
                99,
            )

    @api.depends("qty_available", "min_alert_qty", "type")
    def _compute_alert_status(self):
        for product in self:
            if product.type == "product" and product.qty_available < (product.min_alert_qty or 0.0):
                product.alert_status = "low"
                product.is_low_stock = True
            else:
                product.alert_status = "normal"
                product.is_low_stock = False

    def _search_low_stock(self, operator, value):
        if operator not in ["=", "!="]:
            raise NotImplementedError(_("Operation %s not implemented.") % operator)

        products = self.search([("type", "=", "product")])
        low_stock_ids = []
        for product in products:
            if product.qty_available < (product.min_alert_qty or 0.0):
                low_stock_ids.append(product.id)

        if (operator == "=" and value is True) or (operator == "!=" and value is False):
            return [("id", "in", low_stock_ids)]
        return [("id", "not in", low_stock_ids)]

    def action_next_purchase_status(self):
        _cycle = {
            "no_order": "ordered",
            "ordered": "stock_received",
            "stock_received": "no_order",
        }
        for product in self:
            current = product.purchase_status or "no_order"
            next_status = _cycle.get(current, "ordered")

            if next_status == "stock_received" and product.type == "product" and product.qty_available < 5.0:
                next_status = "no_order"

            product.purchase_status = next_status

            if next_status == "ordered":
                product.purchase_order_date = fields.Date.context_today(product)
            elif next_status == "no_order":
                product.purchase_order_date = False

    def _set_purchase_status_if_needed(self, status, clear_order_date=False):
        products_to_update = self.filtered(lambda p: p.purchase_status != status)
        if not products_to_update:
            return

        vals = {"purchase_status": status}
        if clear_order_date:
            vals["purchase_order_date"] = False
        products_to_update.write(vals)

    def _auto_mark_purchase_received(self):
        storable_products = self.filtered(lambda p: p.type == "product")
        sufficient_stock_products = storable_products.filtered(
            lambda p: p.qty_available >= (p.min_alert_qty or 0.0)
        )
        low_stock_products = storable_products - sufficient_stock_products

        sufficient_stock_products._set_purchase_status_if_needed("stock_received")
        low_stock_products.filtered(
            lambda p: p.purchase_status != "ordered"
        )._set_purchase_status_if_needed("no_order", clear_order_date=True)

    def _auto_reset_purchase_status_for_low_stock(self):
        low_stock_products = self.filtered(
            lambda p: p.type == "product"
            and p.purchase_status != "ordered"
            and p.qty_available < (p.min_alert_qty or 0.0)
        )
        low_stock_products._set_purchase_status_if_needed("no_order", clear_order_date=True)

    @api.model
    def cron_update_purchase_status_for_low_stock(self):
        products = self.search([("type", "=", "product")])
        products._auto_reset_purchase_status_for_low_stock()
