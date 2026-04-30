from odoo import api, fields, models
from odoo.exceptions import UserError



class StockPicking(models.Model):
    _inherit = "stock.picking"

    state = fields.Selection(
        selection_add=[("done", "Packed")],
    )

    def _auto_init(self):
        self.env.cr.execute("""
            ALTER TABLE stock_picking DROP CONSTRAINT IF EXISTS stock_picking_packed_by_fkey;
            ALTER TABLE stock_picking DROP CONSTRAINT IF EXISTS stock_picking_packed_by_user_fkey;
        """)
        return super()._auto_init()
    packed_by = fields.Char(
        string="Packed By (Partner)",
        copy=False,
    )
    packed_by_user = fields.Char(
        string="Packed By",
        copy=False,
    )
    delivered_by = fields.Many2one(
        "res.users",
        string="Delivered By",
        copy=False,
        readonly=True,
    )
    packed_notes = fields.Text(
        string="Packing Notes",
        copy=False,
    )
    delivered_notes = fields.Text(
        string="Delivered Notes",
        copy=False,
    )
    is_packing_restricted_user = fields.Boolean(
        compute="_compute_is_packing_restricted_user",
    )
    dispatch_mode_id = fields.Many2one(
        "packing.dispatch.mode",
        string="Dispatch Mode",
        related="sale_id.dispatch_mode_id",
        store=False,
    )
    sale_special_delivery_note = fields.Text(
        string="Quotation/Sales Note",
        related="sale_id.special_delivery_note",
        readonly=True,
    )
    shipping_count = fields.Integer(
        string="Shipping Count",
        compute="_compute_shipping_count",
    )

    def _is_packing_restricted_user(self):
        user = self.env.user
        return user.has_group("DW_BMS.group_packing_team") and not (
            user.has_group("DW_BMS.group_bms_admin")
            or user.has_group("DW_BMS.group_bms_inventory")
            or user.has_group("base.group_system")
        )

    def _compute_is_packing_restricted_user(self):
        restricted = self._is_packing_restricted_user()
        for picking in self:
            picking.is_packing_restricted_user = restricted

    def _get_shipping_invoices(self):
        self.ensure_one()
        if not self.sale_id:
            return self.env["account.move"]
        invoices = self.sudo().sale_id.invoice_ids.filtered(
            lambda move: move.move_type in ("out_invoice", "out_refund") and move.state != "cancel"
        )
        posted_invoices = invoices.filtered(lambda move: move.state == "posted")
        return posted_invoices or invoices

    @api.depends("sale_id", "sale_id.invoice_ids.shipping_ids", "sale_id.invoice_ids.state")
    def _compute_shipping_count(self):
        shipping_model = self.env["shipping.management"].sudo()
        for picking in self:
            invoice_ids = picking._get_shipping_invoices().ids if picking.sale_id else []
            if not invoice_ids:
                picking.shipping_count = 0
                continue
            picking.shipping_count = shipping_model.search_count([
                "|",
                ("picking_id", "=", picking.id),
                ("invoice_id", "in", invoice_ids),
            ])

    def _get_default_customer_location(self):
        return self.env.ref("stock.stock_location_customers", raise_if_not_found=False)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        picking_type_id = vals.get("picking_type_id") or self.env.context.get("default_picking_type_id")
        picking_type = self.env["stock.picking.type"].browse(picking_type_id)
        if (
            picking_type
            and picking_type.code == "outgoing"
            and not vals.get("location_dest_id")
            and "location_dest_id" in fields_list
        ):
            customer_location = self._get_default_customer_location()
            if customer_location:
                vals["location_dest_id"] = customer_location.id
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        if self._is_packing_restricted_user():
            raise UserError("Packing Team users are not allowed to create deliveries.")

        customer_location = self._get_default_customer_location()
        for vals in vals_list:
            picking_type_id = vals.get("picking_type_id") or self.env.context.get("default_picking_type_id")
            picking_type = self.env["stock.picking.type"].browse(picking_type_id)
            if picking_type and picking_type.code == "outgoing" and not vals.get("location_dest_id") and customer_location:
                vals["location_dest_id"] = customer_location.id

        pickings = super().create(vals_list)
        return pickings

    def write(self, vals):
        res = super().write(vals)
        return res



    def button_validate(self):
        res = super().button_validate()

        done_pickings = self.filtered(lambda picking: picking.state == "done")
        if not done_pickings:
            return res

        done_pickings.write({"delivered_by": self.env.user.id})

        for picking in done_pickings:
            if picking.sale_id:
                picking.env['activity.timeline'].create({
                    'quotation_id': picking.sale_id.id,
                    'activity_type': 'delivery',
                    'description': f'Delivery {picking.name} validated.',
                    'status': 'Packed',
                })

        moved_products = done_pickings.move_ids_without_package.mapped("product_id").filtered(
            lambda product: product.type == "product"
        )
        if not moved_products:
            return res

        incoming_products = done_pickings.filtered(
            lambda picking: picking.picking_type_id.code == "incoming"
        ).move_ids_without_package.mapped("product_id")
        if incoming_products:
            incoming_products._auto_mark_purchase_received()

        moved_products._auto_reset_purchase_status_for_low_stock()

        return res

    def unlink(self):
        if self._is_packing_restricted_user():
            raise UserError("Packing Team users are not allowed to delete deliveries.")
        return super().unlink()

    def action_open_packing_order(self):
        self.ensure_one()
        if not self.sale_id:
            raise UserError("Only Deliveries linked to a Quotation/Sale Order have a packing order.")
        
        packing = self.env["packing.order"].search([("sale_order_id", "=", self.sale_id.id)], limit=1)
        if not packing:
            raise UserError("The Packing Order has not been generated from the Quotation yet.")

        view_id = self.env.ref("DW_BMS.view_packing_order_form_readonly").id
        return {
            "type": "ir.actions.act_window",
            "name": "Packing (Read-Only)",
            "res_model": "packing.order",
            "res_id": packing.id,
            "view_mode": "form",
            "views": [(view_id, "form")],
            "target": "current",
        }

    def action_open_shipping(self):
        self.ensure_one()
        if not self.sale_id:
            raise UserError("Only deliveries linked to a quotation or sale order can open Shipping.")

        invoices = self._get_shipping_invoices()
        if not invoices:
            raise UserError(
                "No customer invoice was found for this delivery.\n"
                "Please create the invoice first, then open Shipping."
            )

        shipping_model = self.env["shipping.management"]
        shipping = shipping_model.search([("picking_id", "=", self.id)], order="id desc", limit=1)
        if not shipping:
            shipping = shipping_model.search(
                [("invoice_id", "in", invoices.ids)],
                order="id desc",
                limit=1,
            )

        default_invoice = invoices[:1]
        return {
            "type": "ir.actions.act_window",
            "name": "Shipping Management",
            "view_mode": "form",
            "res_model": "shipping.management",
            "res_id": shipping.id if shipping else False,
            "context": {
                "default_invoice_id": default_invoice.id,
                "default_picking_id": self.id,
            },
        }
