from odoo import api, fields, models

class ActivityTimeline(models.Model):
    _name = 'activity.timeline'
    _description = 'Quotation Activity Timeline'
    _order = 'datetime desc, id desc'

    quotation_id = fields.Many2one('sale.order', string='Quotation', required=True, ondelete='cascade')
    activity_type = fields.Selection([
        ('quotation', 'Quotation'),
        ('sale', 'Sale'),
        ('delivery', 'Delivery'),
        ('invoice', 'Invoice'),
        ('shipping', 'Shipping'),
        ('update', 'Update')
    ], string='Type', required=True)
    description = fields.Char(string='Description', required=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user)
    datetime = fields.Datetime(string='Date & Time', default=fields.Datetime.now)
    notes = fields.Text(string='Notes')
    tracking_link = fields.Char(string='Tracking Link')
    shipping_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('shipped', 'Shipped'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('complaint', 'Complaint'),
        ('rto', 'RTO'),
        ('rto_received', 'RTO Received')
    ], string='Shipping Status')
    status = fields.Char(string='Status')
