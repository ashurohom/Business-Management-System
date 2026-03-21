from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_open_packing_order(self):
        self.ensure_one()

        packing = self.env["packing.order"].create({
            "sale_order_id": self.id,
            "company_id": self.company_id.id,
            "company_address": self.company_id.partner_id.contact_address or "",
            "partner_id": self.partner_id.id,
            "customer_address": self.partner_id.contact_address or "",
            "packing_line_ids": [
                (0, 0, {
                    "product_id": line.product_id.id,
                    "description": line.name,
                    "quantity": line.product_uom_qty,
                    "uom_id": line.product_uom.id,
                })
                for line in self.order_line.filtered(lambda l: not l.display_type and l.product_id)
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
