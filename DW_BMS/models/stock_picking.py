from odoo import api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    state = fields.Selection(
        selection_add=[("packed", "Packed"), ("done",)],
        ondelete={"packed": lambda records: records.write({"state": "assigned"})},
    )
    packed_by = fields.Many2one(
        "res.partner",
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

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.has_group("DW_BMS.group_packing_team"):
            raise UserError("Packing Team users are not allowed to create deliveries.")

        pickings = super().create(vals_list)
        pickings._update_state_for_packed_by()
        return pickings

    def write(self, vals):
        res = super().write(vals)
        if "packed_by" in vals:
            self._update_state_for_packed_by()
        return res

    @api.onchange("packed_by")
    def _onchange_packed_by(self):
        for picking in self:
            if picking.packed_by and picking.state not in ("waiting", "done", "cancel"):
                picking.state = "packed"

    def _update_state_for_packed_by(self):
        pickings_to_pack = self.filtered(
            lambda picking: picking.packed_by and picking.state not in ("waiting", "done", "cancel")
        )
        if pickings_to_pack:
            pickings_to_pack.with_context(skip_packed_state_update=True).write({"state": "packed"})

    def button_validate(self):
        res = super().button_validate()

        done_pickings = self.filtered(lambda picking: picking.state == "done")
        if not done_pickings:
            return res

        done_pickings.write({"delivered_by": self.env.user.id})

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
        if self.env.user.has_group("DW_BMS.group_packing_team"):
            raise UserError("Packing Team users are not allowed to delete deliveries.")
        return super().unlink()
