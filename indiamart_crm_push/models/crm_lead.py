from odoo import fields, models


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    x_indiamart_query_id = fields.Char(string='IndiaMART Query ID', index=True, copy=False)
    x_indiamart_source = fields.Char(string='IndiaMART Source', copy=False)
    x_indiamart_raw_data = fields.Text(string='IndiaMART Raw Data', copy=False)