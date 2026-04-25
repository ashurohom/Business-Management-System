
from odoo import models, fields, api

class JobWorkDashboard(models.Model):
    _name = 'dw.job.work.dashboard'

    contractor_id = fields.Many2one('res.partner')
    total_remaining = fields.Float(compute='_compute')

    def _compute(self):
        for rec in self:
            slips = self.env['dw.job.work.issue'].search([
                ('contractor_id','=',rec.contractor_id.id)
            ])
            rec.total_remaining = sum(slips.mapped('remaining_qty'))
