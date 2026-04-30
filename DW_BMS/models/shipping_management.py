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
    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        copy=False,
        ondelete='set null',
        domain=[('picking_type_code', '=', 'outgoing')],
    )
    invoice_number = fields.Char(
        string='Invoice Number',
        related='invoice_id.name',
        store=True,
        readonly=True,
    )
    delivery_number = fields.Char(
        string='Delivery Number',
        related='picking_id.name',
        store=True,
        readonly=True,
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

    packing_notes = fields.Text(
        string='Packing Notes',
        compute='_compute_packing_notes',
        store=False,
        help='Packing notes from the related delivery order (read-only).',
    )

    @api.depends('invoice_id', 'invoice_id.invoice_line_ids')
    def _compute_packing_notes(self):
        for rec in self:
            notes = False
            if rec.invoice_id:
                # Navigate: invoice → sale order → outgoing picking
                sale_orders = rec.invoice_id.invoice_line_ids.sale_line_ids.order_id
                for order in sale_orders:
                    picking = order.picking_ids.filtered(
                        lambda p: p.picking_type_code == 'outgoing'
                    )[:1]
                    if picking and picking.packed_notes:
                        notes = picking.packed_notes
                        break
            rec.packing_notes = notes

    def name_get(self):
        return [(rec.id, f"Shipment - {rec.invoice_id.name or 'New'}") for rec in self]

    def action_mark_delivered(self):
        for rec in self:
            rec.shipping_status = 'delivered'

    def action_cancel(self):
        for rec in self:
            rec.shipping_status = 'cancel'

    def _get_related_sale_orders(self):
        self.ensure_one()
        return self.invoice_id.invoice_line_ids.sale_line_ids.order_id

    def _get_related_outgoing_pickings(self):
        self.ensure_one()
        sale_orders = self._get_related_sale_orders()
        return sale_orders.picking_ids.filtered(lambda picking: picking.picking_type_code == 'outgoing')

    def _sync_related_delivery_order(self):
        for shipping in self:
            if shipping.picking_id:
                continue
            shipping.picking_id = shipping._get_related_outgoing_pickings()[:1].id or False

    def _update_picking_shipping_status(self):
        """
        Push the current shipping_status to the latest_shipping_status field
        on all outgoing stock.picking records linked to the same sale order.
        This keeps the stored field in sync for the packing team record rule.
        """
        for shipping in self:
            pickings = shipping._get_related_outgoing_pickings()
            if shipping.picking_id:
                pickings |= shipping.picking_id
            if pickings:
                pickings.write({'latest_shipping_status': shipping.shipping_status})

    @api.model_create_multi
    def create(self, vals_list):
        shippings = super().create(vals_list)
        shippings._sync_related_delivery_order()
        for shipping in shippings:
            sale_orders = shipping._get_related_sale_orders()
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
        # Sync latest_shipping_status on related pickings
        shippings._update_picking_shipping_status()
        return shippings

    def write(self, vals):
        res = super().write(vals)
        if 'invoice_id' in vals and 'picking_id' not in vals:
            self._sync_related_delivery_order()
        if 'shipping_status' in vals or 'tracking_link' in vals:
            for shipping in self:
                sale_orders = shipping._get_related_sale_orders()
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
        # Sync latest_shipping_status on related pickings whenever status changes
        if 'shipping_status' in vals:
            self._update_picking_shipping_status()
        return res
