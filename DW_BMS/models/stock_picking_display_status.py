# -*- coding: utf-8 -*-

from odoo import api, fields, models


# Shipping status label map (mirrors shipping.management selection)
_SHIPPING_STATUS_LABELS = {
    'shipped':          'Shipped',
    'in_transit':       'In Transit',
    'out_for_delivery': 'Out for Delivery',
    'delivered':        'Delivered',
    'cancel':           'Cancelled',
    'complaint':        'Complaint',
    'rto':              'RTO',
    'rto_received':     'RTO Received',
}


class StockPickingDisplayStatus(models.Model):
    """
    Extends stock.picking with a single computed 'display_status' field that
    combines the standard inventory state with the latest shipping status.

    Why store=False:
      shipping.management has invoice_id (Many2one → account.move), but
      account.move does NOT have a shipping_management_ids One2many back.
      Therefore we cannot use @api.depends across that boundary in a stored
      field.  store=False (non-stored computed) re-evaluates on each read, which
      is the correct and safe approach here.

    Logic:
      - state != 'done'  →  standard picking state label
      - state == 'done'  →  latest shipping.management status for this picking's
                            sale order invoices.  Fallback: "Packed"
    """

    _inherit = "stock.picking"

    # ─────────────────────────────────────────────────────────────────────────
    # Fields  (store=False — avoids cross-model @api.depends limitation)
    # ─────────────────────────────────────────────────────────────────────────

    display_status = fields.Char(
        string="Status",
        compute="_compute_display_status",
        store=False,
    )

    # Responsible — the salesperson who created the linked sale order.
    # Related + stored so it can be shown in the tree view without ORM issues.
    sale_responsible_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        related="sale_id.user_id",
        store=True,
        readonly=True,
    )

    # Raw key used for badge colour decorations in XML (not shown as a column)
    display_status_key = fields.Char(
        string="Status Key",
        compute="_compute_display_status",
        search="_search_display_status_key",
        store=False,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Stored shipping status — used in ir.rule domain for packing team
    # visibility. Updated programmatically from shipping.management create/write.
    # Cannot be a computed+stored field because account.move has no
    # shipping_management_ids One2many to depend on.
    # ─────────────────────────────────────────────────────────────────────────

    latest_shipping_status = fields.Selection(
        [
            ('shipped',          'Shipped'),
            ('in_transit',       'In Transit'),
            ('out_for_delivery', 'Out for Delivery'),
            ('delivered',        'Delivered'),
            ('cancel',           'Cancelled'),
            ('complaint',        'Complaint'),
            ('rto',              'RTO'),
            ('rto_received',     'RTO Received'),
        ],
        string="Shipping Status (Stored)",
        store=True,
        copy=False,
        help="Latest shipping status from shipping.management. "
             "Used by packing team record rule to hide delivered/cancelled deliveries.",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Compute  — only depends on fields that actually exist on stock.picking /
    #           sale.order / account.move (no cross-model One2many needed)
    # ─────────────────────────────────────────────────────────────────────────

    @api.depends(
        "state",
        "sale_id",
        "sale_id.invoice_ids",
        "sale_id.invoice_ids.state",
    )
    def _compute_display_status(self):
        # Build state label dict once from the selection definition
        state_labels = dict(self._fields["state"].selection)

        for rec in self:
            if rec.state != "done":
                # ── Not yet packed: show standard inventory state label ──────
                rec.display_status = state_labels.get(rec.state, rec.state or "")
                rec.display_status_key = rec.state or ""
            else:
                # ── Packed: try to get latest shipping status ────────────────
                shipping_status = rec._get_latest_shipping_status()
                if shipping_status:
                    rec.display_status = _SHIPPING_STATUS_LABELS.get(
                        shipping_status, shipping_status
                    )
                    rec.display_status_key = shipping_status
                else:
                    rec.display_status = "Packed"
                    rec.display_status_key = "packed"

    # ─────────────────────────────────────────────────────────────────────────
    # Helper
    # ─────────────────────────────────────────────────────────────────────────

    def _get_latest_shipping_status(self):
        """
        Return the shipping_status key from the most recent shipping.management
        record linked to the invoices of the related sale order.

        Resolution:
          1. Collect posted out_invoices from sale_id.invoice_ids
          2. Search shipping.management where invoice_id in those invoices
          3. Return the shipping_status of the most recent record (highest id)

        Returns:
            str | False
        """
        self.ensure_one()

        if not self.sale_id:
            return False

        # Gather customer invoices linked to this sale order
        invoices = self.sale_id.invoice_ids.filtered(
            lambda inv: inv.move_type == "out_invoice"
        )
        if not invoices:
            return False

        # Prefer posted invoices for shipping lookup
        posted = invoices.filtered(lambda inv: inv.state == "posted")
        lookup_invoices = posted if posted else invoices

        # Search shipping.management with sudo() — this is an internal system
        # lookup. Packing Team has no direct access to shipping.management,
        # but the computed display_status field needs to read it.
        shipping = self.env["shipping.management"].sudo().search(
            [("invoice_id", "in", lookup_invoices.ids)],
            order="id desc",
            limit=1,
        )
        return shipping.shipping_status if shipping else False

    @api.model
    def _get_done_picking_status_key_map(self, pickings):
        """
        Batch-resolve the display status key for done pickings using the same
        logic as the badge column:
          - latest shipping status if present
          - otherwise 'packed'
        """
        result = {}
        done_pickings = pickings.filtered(lambda p: p.state == "done")
        if not done_pickings:
            return result

        for picking in done_pickings.filtered(lambda p: not p.sale_id):
            result[picking.id] = "packed"

        sales = done_pickings.mapped("sale_id").filtered(bool)
        if not sales:
            return result

        sale_invoice_map = {}
        invoice_to_sale_ids = {}
        invoice_ids = set()

        for sale in sales:
            invoices = sale.invoice_ids.filtered(lambda inv: inv.move_type == "out_invoice")
            posted = invoices.filtered(lambda inv: inv.state == "posted")
            lookup_invoices = posted if posted else invoices
            sale_invoice_map[sale.id] = lookup_invoices.ids
            for invoice in lookup_invoices:
                invoice_ids.add(invoice.id)
                invoice_to_sale_ids.setdefault(invoice.id, set()).add(sale.id)

        latest_status_by_sale = {}
        if invoice_ids:
            shipping_records = self.env["shipping.management"].sudo().search(
                [("invoice_id", "in", list(invoice_ids))],
                order="id desc",
            )
            for shipping in shipping_records:
                for sale_id in invoice_to_sale_ids.get(shipping.invoice_id.id, set()):
                    if sale_id not in latest_status_by_sale:
                        latest_status_by_sale[sale_id] = shipping.shipping_status

        for picking in done_pickings.filtered(lambda p: p.sale_id):
            result[picking.id] = latest_status_by_sale.get(picking.sale_id.id) or "packed"

        return result

    @api.model
    def _search_display_status_key(self, operator, value):
        supported = {"=", "!=", "in", "not in"}
        if operator not in supported:
            return [("id", "=", 0)]

        if operator in {"=", "!="}:
            values = {value}
        else:
            values = set(value or [])

        regular_states = {"draft", "waiting", "confirmed", "assigned", "cancel"}
        done_states = {
            "packed",
            "shipped",
            "in_transit",
            "out_for_delivery",
            "delivered",
            "complaint",
            "rto",
            "rto_received",
        }

        matching_ids = set()

        regular_matches = values & regular_states
        if regular_matches:
            matching_ids.update(self.search([("state", "in", list(regular_matches))]).ids)

        done_matches = values & done_states
        if done_matches:
            done_pickings = self.search([("state", "=", "done")])
            status_key_map = self._get_done_picking_status_key_map(done_pickings)
            matching_ids.update(
                picking_id
                for picking_id, status_key in status_key_map.items()
                if status_key in done_matches
            )

        if operator in {"=", "in"}:
            return [("id", "in", list(matching_ids) or [0])]
        return [("id", "not in", list(matching_ids))]
