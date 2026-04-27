from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class JobWorkIssue(models.Model):
    _name = "dw.job.work.issue"
    _description = "Job Work Issue"
    _order = "issue_date desc, id desc"

    name = fields.Char(
        string="Slip Number",
        default="New",
        copy=False,
        readonly=True,
    )
    issue_date = fields.Datetime(
        string="Issue Date",
        default=fields.Datetime.now,
        required=True,
    )
    contractor_id = fields.Many2one(
        "res.partner",
        string="Contractor",
        required=True,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("confirmed", "Confirmed")],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
    )
    line_ids = fields.One2many(
        "dw.job.work.issue.line",
        "issue_id",
        string="Materials",
        copy=True,
    )
    remaining_qty = fields.Float(
        string="Remaining Quantity",
        compute="_compute_remaining_qty",
        store=True,
    )

    @api.depends("line_ids.remaining_qty")
    def _compute_remaining_qty(self):
        for rec in self:
            rec.remaining_qty = sum(rec.line_ids.mapped("remaining_qty"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("dw.job.work") or "New"
        return super().create(vals_list)

    def action_confirm(self):
        stock_location = self.env.ref("stock.stock_location_stock")
        job_work_location = self.env.ref("DW_JOB_WORK.job_work_location")

        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.line_ids:
                raise ValidationError(_("Add at least one raw material line before confirming."))

            move_vals_list = []
            for line in rec.line_ids:
                if line.qty <= 0:
                    raise ValidationError(
                        _("Issued quantity must be greater than zero for all raw materials.")
                    )
                move_vals_list.append(
                    {
                        "name": rec.name,
                        "product_id": line.product_id.id,
                        "product_uom_qty": line.qty,
                        "product_uom": line.product_id.uom_id.id,
                        "location_id": stock_location.id,
                        "location_dest_id": job_work_location.id,
                        "company_id": self.env.company.id,
                    }
                )
                line.remaining_qty = line.qty

            moves = self.env["stock.move"].create(move_vals_list)
            moves._action_confirm()
            moves._action_assign()
            for move in moves:
                move.quantity = move.product_uom_qty
                move.picked = True
            moves._action_done()
            rec.state = "confirmed"


class JobWorkIssueLine(models.Model):
    _name = "dw.job.work.issue.line"
    _description = "Job Work Issue Line"
    _order = "issue_id, id"

    issue_id = fields.Many2one(
        "dw.job.work.issue",
        string="Issue Slip",
        required=True,
        ondelete="cascade",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Raw Material",
        required=True,
    )
    product_free_qty = fields.Float(
        string="Free Quantity",
        compute="_compute_product_free_qty",
        readonly=True,
    )
    qty = fields.Float(string="Issued Quantity", required=True)
    remaining_qty = fields.Float(
        string="Remaining Quantity",
        readonly=True,
        copy=False,
    )
    state = fields.Selection(related="issue_id.state", store=True, readonly=True)
    issue_date = fields.Datetime(related="issue_id.issue_date", store=True, readonly=True)

    @api.depends("product_id")
    def _compute_product_free_qty(self):
        stock_location = self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        for rec in self:
            rec.product_free_qty = 0.0
            if not rec.product_id:
                continue
            product = rec.product_id
            if stock_location:
                product = product.with_context(location=stock_location.id)
            rec.product_free_qty = product.free_qty

    @api.constrains("qty")
    def _check_qty(self):
        for rec in self:
            if rec.qty <= 0:
                raise ValidationError(_("Issued quantity must be greater than zero."))
