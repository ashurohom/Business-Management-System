# -*- coding: utf-8 -*-
"""
dw_bms / models / invoice_import_log.py

Stores a record for each XLSX import batch.
Every batch has a set of log lines — one per invoice in the XLSX.
"""

from odoo import fields, models, api


class DwInvoiceImportLog(models.Model):
    """
    One record per upload / import batch.
    Aggregates summary counters and links to individual line results.
    """
    _name = "dw.invoice.import.log"
    _description = "Invoice Import Log"
    _order = "import_date desc"
    _rec_name = "name"

    # ─── Identity ────────────────────────────────────────────────────────────
    name = fields.Char(
        string="Batch Reference",
        required=True,
        copy=False,
        readonly=True,
        default="New",
    )
    import_date = fields.Datetime(
        string="Import Date",
        default=fields.Datetime.now,
        readonly=True,
    )
    filename = fields.Char(string="File Name", readonly=True)

    # ─── Summary Counters ────────────────────────────────────────────────────
    total_invoices = fields.Integer(string="Total Invoices", readonly=True)
    created = fields.Integer(string="Created", readonly=True)
    skipped = fields.Integer(string="Skipped (Duplicate)", readonly=True)
    failed = fields.Integer(string="Failed", readonly=True)

    # ─── State ───────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ("done", "Done"),
            ("partial", "Partial (Some Failed)"),
        ],
        string="Status",
        default="done",
        readonly=True,
    )

    # ─── Lines ───────────────────────────────────────────────────────────────
    log_line_ids = fields.One2many(
        comodel_name="dw.invoice.import.log.line",
        inverse_name="log_id",
        string="Import Lines",
        readonly=True,
    )

    # ─── ORM ─────────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "dw.invoice.import.log"
                ) or "IMP/0001"
        return super().create(vals_list)


class DwInvoiceImportLogLine(models.Model):
    """
    One record per invoice number processed during an import batch.
    Stores status (created / skipped / failed) and links to the resulting
    account.move when creation succeeded.
    """
    _name = "dw.invoice.import.log.line"
    _description = "Invoice Import Log Line"
    _order = "id asc"

    log_id = fields.Many2one(
        comodel_name="dw.invoice.import.log",
        string="Import Batch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    invoice_number = fields.Char(string="Invoice Number", required=True)
    status = fields.Selection(
        selection=[
            ("created", "Created"),
            ("skipped", "Skipped"),
            ("failed", "Failed"),
        ],
        string="Status",
        required=True,
    )
    message = fields.Text(string="Message / Reason")
    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        ondelete="set null",
    )
