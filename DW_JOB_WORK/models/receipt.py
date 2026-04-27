from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class JobWorkReceipt(models.Model):
    _name = "dw.job.work.receipt"
    _description = "Job Work Receipt"
    _order = "receipt_date desc, id desc"

    receipt_date = fields.Datetime(
        string="Receipt Date",
        default=fields.Datetime.now,
        required=True,
    )
    contractor_id = fields.Many2one(
        "res.partner",
        string="Contractor",
        required=True,
    )
    raw_material_product_id = fields.Many2one(
        "product.product",
        string="Raw Material",
        required=True,
    )
    available_qty = fields.Float(
        string="Available Raw Material",
        compute="_compute_available_qty",
        readonly=True,
    )
    qty_used = fields.Float(string="Raw Material Used", required=True)
    finished_product_id = fields.Many2one(
        "product.product",
        string="Finished Product",
        required=True,
    )
    qty_produced = fields.Float(string="Finished Quantity", required=True)
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )

    @api.depends("contractor_id", "raw_material_product_id")
    def _compute_available_qty(self):
        line_model = self.env["dw.job.work.issue.line"]
        for rec in self:
            rec.available_qty = 0.0
            if not rec.contractor_id or not rec.raw_material_product_id:
                continue
            grouped = line_model.read_group(
                [
                    ("issue_id.contractor_id", "=", rec.contractor_id.id),
                    ("issue_id.state", "=", "confirmed"),
                    ("product_id", "=", rec.raw_material_product_id.id),
                    ("remaining_qty", ">", 0),
                ],
                ["remaining_qty:sum"],
                [],
            )
            rec.available_qty = grouped[0]["remaining_qty"] if grouped else 0.0

    @api.constrains("qty_used", "qty_produced")
    def _check_positive_quantities(self):
        for rec in self:
            if rec.qty_used <= 0:
                raise ValidationError(_("Raw material used must be greater than zero."))
            if rec.qty_produced <= 0:
                raise ValidationError(_("Finished quantity must be greater than zero."))

    def action_confirm(self):
        inventory_location = self.env["stock.location"].sudo().search(
            [("usage", "=", "inventory"), ("company_id", "in", [self.env.company.id, False])],
            limit=1,
        )
        if not inventory_location:
            inventory_location = self.env.ref("stock.location_inventory", raise_if_not_found=False)
        job_work_location = self.env.ref("DW_JOB_WORK.job_work_location")
        stock_location = self.env.ref("stock.stock_location_stock")

        for rec in self:
            if rec.state != "draft":
                continue
            if rec.qty_used > rec.available_qty:
                raise ValidationError(
                    _(
                        "Cannot consume %(used)s because only %(available)s of %(product)s is available for %(contractor)s.",
                        used=rec.qty_used,
                        available=rec.available_qty,
                        product=rec.raw_material_product_id.display_name,
                        contractor=rec.contractor_id.display_name,
                    )
                )

            fifo_lines = self.env["dw.job.work.issue.line"].search(
                [
                    ("issue_id.contractor_id", "=", rec.contractor_id.id),
                    ("issue_id.state", "=", "confirmed"),
                    ("product_id", "=", rec.raw_material_product_id.id),
                    ("remaining_qty", ">", 0),
                ],
                order="issue_date asc, id asc",
            )

            remaining_to_consume = rec.qty_used
            for line in fifo_lines:
                if remaining_to_consume <= 0:
                    break
                consume_now = min(line.remaining_qty, remaining_to_consume)
                line.remaining_qty -= consume_now
                remaining_to_consume -= consume_now

            if remaining_to_consume > 0:
                raise ValidationError(_("Not enough material available to complete this receipt."))

            raw_move = self.env["stock.move"].create(
                {
                    "name": _("%s Raw Consumption", rec.contractor_id.display_name),
                    "product_id": rec.raw_material_product_id.id,
                    "product_uom_qty": rec.qty_used,
                    "product_uom": rec.raw_material_product_id.uom_id.id,
                    "location_id": job_work_location.id,
                    "location_dest_id": inventory_location.id,
                    "company_id": self.env.company.id,
                    "is_inventory": True,
                }
            )
            raw_move._action_confirm()
            raw_move.quantity = rec.qty_used
            raw_move.picked = True
            raw_move._action_done()

            finished_move = self.env["stock.move"].create(
                {
                    "name": _("%s Finished Receipt", rec.contractor_id.display_name),
                    "product_id": rec.finished_product_id.id,
                    "product_uom_qty": rec.qty_produced,
                    "product_uom": rec.finished_product_id.uom_id.id,
                    "location_id": inventory_location.id,
                    "location_dest_id": stock_location.id,
                    "company_id": self.env.company.id,
                    "is_inventory": True,
                }
            )
            finished_move._action_confirm()
            finished_move.quantity = rec.qty_produced
            finished_move.picked = True
            finished_move._action_done()
            rec.state = "confirmed"
