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
            ('shipped', 'Shipped'),
            ('in_transit', 'In Transit'),
            ('out_for_delivery', 'Out for Delivery'),
            ('delivered', 'Delivered'),
            ('cancel', 'Cancelled'),
            ('complaint', 'Complaint'),
            ('rto', 'RTO'),
            ('rto_received', 'RTO Received')
        ],
        string='Status',
        default='shipped',
        required=True,
        copy=False,
    )
    complaint = fields.Char(string='Complaint', copy=False)
    delivery_notes = fields.Char(string='Notes', copy=False)
    vehicle_number = fields.Char(string='Vehicle Number', copy=False)
    transporter_name = fields.Char(string='Transporter Name', copy=False)
    transporter_mobile = fields.Char(string='Transporter Mobile', copy=False)

    def name_get(self):
        return [(rec.id, f"Shipment - {rec.invoice_id.name or 'New'}") for rec in self]

    def action_mark_delivered(self):
        for rec in self:
            rec.shipping_status = 'delivered'

    def action_cancel(self):
        for rec in self:
            rec.shipping_status = 'cancel'

    @api.model_create_multi
    def create(self, vals_list):
        shippings = super().create(vals_list)
        for shipping in shippings:
            sale_orders = shipping.invoice_id.invoice_line_ids.sale_line_ids.order_id
            for order in sale_orders:
                status_dict = dict(shipping._fields['shipping_status'].selection)
                status_label = status_dict.get(shipping.shipping_status, shipping.shipping_status)
                
                mapped_status = shipping.shipping_status
                if mapped_status == 'cancel': mapped_status = 'cancelled'

                self.env['activity.timeline'].create({
                    'quotation_id': order.id,
                    'activity_type': 'shipping',
                    'description': f'Shipping created with status {status_label}.',
                    'tracking_link': shipping.tracking_link,
                    'notes': shipping.delivery_notes or False,
                    'shipping_status': mapped_status if mapped_status in ['shipped', 'in_transit', 'out_for_delivery', 'delivered', 'cancelled', 'complaint', 'rto', 'rto_received'] else False,
                    'status': status_label,
                })
        return shippings

    def write(self, vals):
        res = super().write(vals)
        if 'shipping_status' in vals or 'tracking_link' in vals:
            for shipping in self:
                sale_orders = shipping.invoice_id.invoice_line_ids.sale_line_ids.order_id
                for order in sale_orders:
                    status_dict = dict(shipping._fields['shipping_status'].selection)
                    status_label = status_dict.get(shipping.shipping_status, shipping.shipping_status)
                    
                    mapped_status = shipping.shipping_status
                    if mapped_status == 'cancel': mapped_status = 'cancelled'
                    
                    self.env['activity.timeline'].create({
                        'quotation_id': order.id,
                        'activity_type': 'shipping',
                        'description': f'Shipping updated to status {status_label}.',
                        'tracking_link': shipping.tracking_link,
                        'notes': shipping.delivery_notes or False,
                        'shipping_status': mapped_status if mapped_status in ['not_started', 'shipped', 'in_transit', 'out_for_delivery', 'delivered', 'cancelled', 'complaint', 'rto', 'rto_received'] else False,
                        'status': status_label,
                    })
        return res
