from odoo import api, fields, models


class ShippingManagement(models.Model):
    _name = 'shipping.management'
    _description = 'Shipping Management'
    _order = 'id desc'

    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        required=True,
        ondelete='cascade',
        domain=lambda self: [('move_type', 'in', ('out_invoice', 'out_refund'))]
    )
    delivered_by = fields.Many2one(
        'res.users',
        string='Delivered By',
        default=lambda self: self.env.user,
        copy=False,
    )
    tracking_id = fields.Char(string='Tracking ID', copy=False)
    tracking_link = fields.Char(string='Tracking Link', copy=False)
    shipping_status = fields.Selection(
        [
            ('in_transit', 'In Transit'),
            ('out_for_delivery', 'Out for Delivery'),
            ('delivered', 'Delivered'),
            ('cancel', 'Cancelled')
        ],
        string='Status',
        default='in_transit',
        required=True,
        copy=False,
    )
    complaint = fields.Char(string='Complaint', copy=False)

    def name_get(self):
        return [(rec.id, f"Shipment - {rec.invoice_id.name or 'New'}") for rec in self]

    def action_mark_delivered(self):
        for rec in self:
            rec.shipping_status = 'delivered'

    def action_cancel(self):
        for rec in self:
            rec.shipping_status = 'cancel'
