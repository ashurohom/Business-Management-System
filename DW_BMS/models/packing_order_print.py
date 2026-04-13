# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class PackingOrderPrint(models.Model):
    """
    Extension of packing.order with print action methods.
    Provides buttons to print the related Sale Order quotation
    and the related Customer Invoice directly from the Packing form.
    """

    _inherit = "packing.order"

    # ─────────────────────────────────────────────────────────────────────────
    # Print Quotation
    # ─────────────────────────────────────────────────────────────────────────

    def action_print_quotation(self):
        """
        Print the Sale Order / Quotation report for the Sale Order linked to
        this Packing Order.

        Raises:
            UserError: If no Sale Order is linked to this record.
        """
        self.ensure_one()

        if not self.sale_order_id:
            raise UserError(
                _("No Sale Order is linked to this Packing Order. "
                  "Please link a Sale Order before printing the quotation.")
            )

        return self.env.ref("DW_BMS.action_report_saleorder_custom_quotation").report_action(
            self.sale_order_id
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Print Invoice
    # ─────────────────────────────────────────────────────────────────────────

    def action_print_invoice(self):
        """
        Print the Customer Invoice (account.move) linked to this Packing Order.

        Resolution order:
          1. The directly linked ``invoice_id`` field on the packing order.
          2. Any posted customer invoice from ``sale_order_id.invoice_ids``.

        Raises:
            UserError: If no invoice can be found.
        """
        self.ensure_one()

        invoice = self._resolve_invoice()

        if not invoice:
            raise UserError(
                _("No invoice found for this Packing Order. "
                  "Please create and confirm an invoice on the related Sale Order first.")
            )

        return self.env.ref("DW_BMS.action_report_invoice_custom").report_action(invoice)

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _resolve_invoice(self):
        """
        Return the best-matching ``account.move`` record for printing.

        Priority:
          1. ``self.invoice_id`` (direct link on the packing order)
          2. Posted customer invoices on ``self.sale_order_id.invoice_ids``
             (first posted invoice, or any draft if none posted yet)

        Returns:
            account.move | empty recordset
        """
        self.ensure_one()

        # 1. Direct link
        if self.invoice_id:
            return self.invoice_id

        # 2. Fetch from the linked Sale Order
        if self.sale_order_id:
            sale_invoices = self.sale_order_id.invoice_ids.filtered(
                lambda inv: inv.move_type == "out_invoice"
            )
            if not sale_invoices:
                return self.env["account.move"]

            # Prefer posted invoices; fall back to the first draft/other state
            posted = sale_invoices.filtered(lambda inv: inv.state == "posted")
            return posted[:1] if posted else sale_invoices[:1]

        return self.env["account.move"]
