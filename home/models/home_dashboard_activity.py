from odoo import fields, models


class HomeDashboardActivity(models.Model):
    _name = "home.dashboard.activity"
    _description = "Home Dashboard Activity"
    _order = "date desc, id desc"

    dashboard_id = fields.Many2one("home.dashboard", required=True, ondelete="cascade")
    type = fields.Char(required=True, readonly=True)
    name = fields.Char(string="Document", required=True, readonly=True)
    user = fields.Char(readonly=True)
    partner = fields.Char(string="Customer/Vendor", readonly=True)
    packed_by = fields.Char(readonly=True)
    delivered_by = fields.Char(readonly=True)
    packing_notes = fields.Text(readonly=True)
    delivered_notes = fields.Text(readonly=True)
    status = fields.Char(readonly=True)
    date = fields.Datetime(readonly=True)
