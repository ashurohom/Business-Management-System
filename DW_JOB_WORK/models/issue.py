
from odoo import models, fields, api

class JobWorkIssue(models.Model):
    _name = 'dw.job.work.issue'
    _description = 'Job Work Issue'

    name = fields.Char(default='New', copy=False)
    contractor_id = fields.Many2one('res.partner', required=True)
    line_ids = fields.One2many('dw.job.work.issue.line','issue_id')
    remaining_qty = fields.Float(default=0)

    @api.model
    def create(self, vals):
        if vals.get('name','New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dw.job.work') or 'New'
        return super().create(vals)

    def action_confirm(self):
        stock = self.env.ref('stock.stock_location_stock')
        job = self.env.ref('dw_job_work.job_work_location')

        for rec in self:
            total = 0
            for l in rec.line_ids:
                total += l.qty
                move = self.env['stock.move'].create({
                    'name': rec.name,
                    'product_id': l.product_id.id,
                    'product_uom_qty': l.qty,
                    'product_uom': l.product_id.uom_id.id,
                    'location_id': stock.id,
                    'location_dest_id': job.id,
                })
                move._action_confirm(); move._action_assign(); move._action_done()
            rec.remaining_qty = total

class JobWorkIssueLine(models.Model):
    _name = 'dw.job.work.issue.line'

    issue_id = fields.Many2one('dw.job.work.issue')
    product_id = fields.Many2one('product.product', required=True)
    qty = fields.Float(required=True)
