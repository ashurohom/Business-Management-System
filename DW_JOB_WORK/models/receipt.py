
from odoo import models, fields
from odoo.exceptions import ValidationError

class JobWorkReceipt(models.Model):
    _name = 'dw.job.work.receipt'

    contractor_id = fields.Many2one('res.partner', required=True)
    product_id = fields.Many2one('product.product')
    qty_used = fields.Float()
    qty_produced = fields.Float()

    def action_confirm(self):
        job = self.env.ref('dw_job_work.job_work_location')
        stock = self.env.ref('stock.stock_location_stock')

        # FIFO slips
        slips = self.env['dw.job.work.issue'].search([
            ('contractor_id','=',self.contractor_id.id),
            ('remaining_qty','>',0)
        ], order='id')

        remaining = self.qty_used

        for s in slips:
            if remaining <= 0:
                break
            if s.remaining_qty >= remaining:
                s.remaining_qty -= remaining
                remaining = 0
            else:
                remaining -= s.remaining_qty
                s.remaining_qty = 0

        if remaining > 0:
            raise ValidationError("Not enough material")

        # consume raw
        self.env['stock.move'].create({
            'name':'Consume',
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty_used,
            'product_uom': self.product_id.uom_id.id,
            'location_id': job.id,
            'location_dest_id': stock.id,
        })._action_done()

        # finished product
        self.env['stock.move'].create({
            'name':'Finished',
            'product_id': self.product_id.id,
            'product_uom_qty': self.qty_produced,
            'product_uom': self.product_id.uom_id.id,
            'location_id': job.id,
            'location_dest_id': stock.id,
        })._action_done()
