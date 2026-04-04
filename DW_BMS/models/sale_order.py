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

    free_qty = fields.Float(
        string="Free Quantity",
        compute="_compute_free_qty",
        store=False,
    )
    stock_qty = fields.Float(related="free_qty", readonly=True)

    @api.depends("product_id", "order_id.warehouse_id")
    def _compute_free_qty(self):
        for line in self:
            if line.product_id:
                line.free_qty = line.product_id.with_context(
                    warehouse=line.order_id.warehouse_id.id
                ).free_qty
            else:
                line.free_qty = 0.0

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
            if not line.product_id or line.display_type or line.product_id.type != 'product':
                continue

            available_free_qty = line.product_id.with_context(
                warehouse=line.order_id.warehouse_id.id
            ).free_qty
            rounding = line.product_uom.rounding or line.product_id.uom_id.rounding or 0.01

            if float_compare(line.product_uom_qty or 0.0, available_free_qty, precision_rounding=rounding) > 0:
                raise ValidationError(
                    "Ordered quantity cannot be more than available free stock (On Hand - Reserved).\n"
                    "Product: %s\n"
                    "Free stock available: %.2f\n"
                    "Entered quantity: %.2f"
                    % (
                        line.product_id.display_name,
                        available_free_qty,
                        line.product_uom_qty or 0.0,
                    )
                )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # ─────────────────────────────────────────────────────────────────
    # Delivery Type choices (same as account.move)
    # ─────────────────────────────────────────────────────────────────
    _DELIVERY_TYPES = [
        ("direct_delivery", "Direct Delivery"),
        ("ship_to_different", "Ship To Different"),
        ("third_party_delivery", "Third Party Delivery"),
    ]

    # ── Delivery / address fields ────────────────────────────────────
    delivery_type = fields.Selection(
        selection=_DELIVERY_TYPES,
        string="Delivery Type",
        default="direct_delivery",
        copy=False,
    )
    bill_to_same_as_customer = fields.Boolean(
        string="Bill To Same as Customer Address",
        default=True,
        copy=False,
    )
    billing_partner_id = fields.Many2one(
        "res.partner",
        string="Billing Partner",
        copy=False,
    )
    billing_customer_name = fields.Char(
        string="Billing Customer Name",
        copy=False,
    )
    billing_mobile = fields.Char(string="Billing Mobile", copy=False)
    bill_to_address = fields.Text(string="Bill To Address", copy=False)
    bill_to_city = fields.Char(string="Bill To City", copy=False)
    bill_to_state_id = fields.Many2one("res.country.state", string="Bill To State", copy=False)
    bill_to_country = fields.Char(string="Bill To Country", copy=False)
    bill_to_zip = fields.Char(string="Bill To PIN Code", copy=False)

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
    shipping_customer_name = fields.Char(
        string="Shipping Customer Name",
        copy=False,
    )
    shipping_mobile = fields.Char(string="Shipping Mobile", copy=False)
    ship_to_address = fields.Text(string="Ship To Address", copy=False)
    ship_to_city = fields.Char(string="Ship To City", copy=False)
    ship_to_state_id = fields.Many2one("res.country.state", string="Ship To State", copy=False)
    ship_to_country = fields.Char(string="Ship To Country", copy=False)
    ship_to_zip = fields.Char(string="Ship To PIN Code", copy=False)

    # ── Weight ───────────────────────────────────────────────────────
    total_products_weight = fields.Float(
        string="Total Products Weight",
        compute="_compute_total_products_weight",
        store=True,
    )

    # ── Activity Timeline ────────────────────────────────────────────
    activity_timeline_ids = fields.One2many(
        'activity.timeline', 'quotation_id', string='Activity Timeline'
    )
    total_activities = fields.Integer(
        string='Total Activities', compute='_compute_activity_stats'
    )
    latest_shipping_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('shipped', 'Shipped'),
        ('in_transit', 'In Transit'),
        ('out_for_delivery', 'Out for Delivery'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('complaint', 'Complaint'),
        ('rto', 'RTO'),
        ('rto_received', 'RTO Received'),
    ], string='Shipping Status', compute='_compute_activity_stats')
    latest_shipping_notes = fields.Text(string='Notes', compute='_compute_activity_stats')
    overall_activity_status = fields.Char(string='Overall Status', compute='_compute_activity_stats')

    @api.depends('activity_timeline_ids.shipping_status', 'activity_timeline_ids.status', 'activity_timeline_ids.notes', 'state')
    def _compute_activity_stats(self):
        for order in self:
            order.total_activities = len(order.activity_timeline_ids)
            shipping_activities = order.activity_timeline_ids.filtered(lambda a: a.activity_type == 'shipping' and a.shipping_status)
            if shipping_activities:
                order.latest_shipping_status = shipping_activities[0].shipping_status
                order.latest_shipping_notes = shipping_activities[0].notes or False
            else:
                order.latest_shipping_status = 'not_started'
                order.latest_shipping_notes = False
                
            if order.activity_timeline_ids:
                order.overall_activity_status = order.activity_timeline_ids[0].status or dict(self._fields['state'].selection).get(order.state, order.state)
            else:
                order.overall_activity_status = dict(self._fields['state'].selection).get(order.state, order.state)


    @api.depends("order_line.product_id.weight", "order_line.product_uom_qty", "order_line.display_type")
    def _compute_total_products_weight(self):
        for order in self:
            order.total_products_weight = sum(
                (line.product_id.weight or 0.0) * line.product_uom_qty
                for line in order.order_line
                if not line.display_type
            )

    # ── _prepare_invoice override ─────────────────────────────────────
    def _prepare_invoice(self):
        vals = super()._prepare_invoice()
        vals["invoice_date"] = fields.Date.context_today(self)
        
        # Pass the address fields over to the invoice
        vals.update({
            "delivery_type": self.delivery_type,
            "bill_to_same_as_customer": self.bill_to_same_as_customer,
            "billing_partner_id": self.billing_partner_id.id if self.billing_partner_id else False,
            "billing_customer_name": self.billing_customer_name,
            "billing_mobile": self.billing_mobile,
            "bill_to_address": self.bill_to_address,
            "bill_to_city": self.bill_to_city,
            "bill_to_state_id": self.bill_to_state_id.id if self.bill_to_state_id else False,
            "bill_to_country": self.bill_to_country,
            "bill_to_zip": self.bill_to_zip,
            "ship_to_same_as_customer": self.ship_to_same_as_customer,
            "shipping_partner_id": self.shipping_partner_id.id if self.shipping_partner_id else False,
            "shipping_customer_name": self.shipping_customer_name,
            "shipping_mobile": self.shipping_mobile,
            "ship_to_address": self.ship_to_address,
            "ship_to_city": self.ship_to_city,
            "ship_to_state_id": self.ship_to_state_id.id if self.ship_to_state_id else False,
            "ship_to_country": self.ship_to_country,
            "ship_to_zip": self.ship_to_zip,
        })
        return vals

    # ─────────────────────────────────────────────────────────────────
    # Address helpers (mirrored from account.move)
    # ─────────────────────────────────────────────────────────────────

    def _partner_address_vals(
        self,
        partner,
        prefix,
        partner_field=None,
        mobile_field=None,
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
        if name_field:
            vals[name_field] = partner.name or False
        return vals

    def _clear_partner_section_vals(self, prefix, partner_field, mobile_field, name_field):
        return self._partner_address_vals(
            False,
            prefix,
            partner_field=partner_field,
            mobile_field=mobile_field,
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
                    name_field="billing_customer_name",
                )
            )
            vals.update(
                self._partner_address_vals(
                    self.partner_id,
                    "ship_to",
                    partner_field="shipping_partner_id",
                    mobile_field="shipping_mobile",
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
                        name_field="shipping_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "ship_to",
                        "shipping_partner_id",
                        "shipping_mobile",
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
                        name_field="billing_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "bill_to",
                        "billing_partner_id",
                        "billing_mobile",
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
                        name_field="shipping_customer_name",
                    )
                )
            else:
                vals.update(
                    self._clear_partner_section_vals(
                        "ship_to",
                        "shipping_partner_id",
                        "shipping_mobile",
                        "shipping_customer_name",
                    )
                )
        return vals

    def _apply_delivery_type_defaults(self):
        for order in self:
            order.update(order._get_delivery_type_default_vals())

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

    # ─────────────────────────────────────────────────────────────────
    # Onchange handlers
    # ─────────────────────────────────────────────────────────────────

    @api.onchange("partner_id")
    def _onchange_partner_id_apply_delivery_defaults(self):
        if self.partner_id:
            self._apply_delivery_type_defaults()

    @api.onchange("delivery_type")
    def _onchange_delivery_type(self):
        self._apply_delivery_type_defaults()

    @api.onchange("bill_to_same_as_customer")
    def _onchange_bill_to_same_as_customer(self):
        if self.bill_to_same_as_customer:
            self.update(
                self._partner_address_vals(
                    self.partner_id,
                    "bill_to",
                    partner_field="billing_partner_id",
                    mobile_field="billing_mobile",
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
                    name_field="shipping_customer_name",
                )
            )



    # ─────────────────────────────────────────────────────────────────
    # Packing action
    # ─────────────────────────────────────────────────────────────────

    def action_open_packing_order(self):
        self.ensure_one()
        packing = self.env["packing.order"].search(
            [("sale_order_id", "=", self.id)], limit=1
        )
        if not packing:
            from_partner, from_address, to_partner, to_address = self._get_packing_addresses()
            packing = self.env["packing.order"].create({
                "sale_order_id": self.id,
                "from_partner_id": from_partner.id if from_partner else False,
                "from_address": from_address,
                "to_partner_id": to_partner.id if to_partner else False,
                "to_address": to_address,
                "packing_line_ids": [
                    (0, 0, {
                        "product_id": line.product_id.id,
                        "description": line.name,
                        "quantity": line.product_uom_qty,
                        "uom_id": line.product_uom.id,
                    })
                    for line in self.order_line.filtered(
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

    # ── Activity Timeline Overrides ──────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order.env['activity.timeline'].create({
                'quotation_id': order.id,
                'activity_type': 'quotation',
                'description': f'Quotation {order.name} created.',
                'status': 'Draft',
            })
        return orders

    def action_confirm(self):
        res = super().action_confirm()
        for order in self:
            order.env['activity.timeline'].create({
                'quotation_id': order.id,
                'activity_type': 'sale',
                'description': f'Sales Order {order.name} confirmed.',
                'status': 'Confirmed',
            })
        return res
