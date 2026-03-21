# -*- coding: utf-8 -*-
"""
dw.invoice.import.column.map — Transient model storing one XLSX column → Odoo field mapping.
One record per column header found in the uploaded XLSX file.
"""

from odoo import fields, models

# Full selection of every destination field the import engine can write to.
# Value 'skip' means "ignore this column".
ODOO_FIELD_SELECTION = [
    ("skip", "── Skip this column ──"),
    # ── Invoice header ─────────────────────────────────────────────────────
    ("invoice_number",   "Invoice Number"),
    ("invoice_date",     "Invoice Date"),
    ("invoice_type",     "Invoice Type"),
    ("customer_name",    "Customer Name"),
    ("customer_gstin",   "GST Number"),
    ("contact_id",       "Contact ID"),
    ("contact_number",   "Contact Number"),
    # ── Payment info ────────────────────────────────────────────────────────
    ("payment_mode",     "Payment Method"),
    ("bank_name",        "Bank Name"),
    ("payment_reference","Payment Reference"),
    ("payment_date",     "Payment Date"),
    ("currency",         "Currency"),
    ("ecommerce_platform", "E-Commerce Platform"),
    ("platform_order_id", "Platform Order ID"),
    ("place_of_supply",  "Place of Supply"),
    # ── E-Invoice ───────────────────────────────────────────────────────────
    ("ack_number",       "E-Invoice ACK No."),
    ("ack_date",         "E-Invoice Date"),
    ("irn_number",       "E-Invoice IRN Number"),
    ("e_invoice_amount", "E-Invoice Amount"),
    # ── E-Way Bill ───────────────────────────────────────────────────────────
    ("eway_bill_number", "E-Way Bill No."),
    ("eway_bill_date",   "E-Way Bill Date"),
    ("eway_bill_amount", "E-Way Bill Amount"),
    # ── Billing address ──────────────────────────────────────────────────────
    ("billing_address",  "Billing Address"),
    ("billing_city",     "Billing City"),
    ("billing_state",    "Billing State"),
    ("billing_country",  "Billing Country"),
    ("billing_pincode",  "Billing Pincode"),
    # ── Shipping address ─────────────────────────────────────────────────────
    ("shipping_address", "Shipping Address"),
    ("shipping_city",    "Shipping City"),
    ("shipping_state",   "Shipping State"),
    ("shipping_country", "Shipping Country"),
    ("shipping_pincode", "Shipping Pincode"),
    # ── Product line ─────────────────────────────────────────────────────────
    ("product_name",     "Product Name"),
    ("product_sku",      "Product SKU"),
    ("product_storage_location", "Product Location"),
    ("hsn_code",         "HSN Code"),
    ("quantity",         "Quantity"),
    ("unit_of_measure",  "Unit (UOM)"),
    ("unit_price",       "Unit Price"),
    ("discount_percent", "Discount (%)"),
    # ── Tax rates ────────────────────────────────────────────────────────────
    ("cgst_rate",        "CGST Rate (%)"),
    ("sgst_rate",        "SGST Rate (%)"),
    ("igst_rate",        "IGST Rate (%)"),
    ("tax_percent",      "Total Tax (%)"),
    ("total_tax_amount", "Total Tax Amount"),
    # ── Tax amounts ──────────────────────────────────────────────────────────
    ("cgst_amount",      "CGST Amount"),
    ("sgst_amount",      "SGST Amount"),
    ("igst_amount",      "IGST Amount"),
    # ── Totals ───────────────────────────────────────────────────────────────
    ("taxable_value",    "Taxable Value"),
    ("price_with_tax",   "Price incl. Tax"),
    ("line_total",       "Line Total"),
    ("grand_total",      "Grand Total"),
]


class DwInvoiceImportColumnMap(models.TransientModel):
    _name = "dw.invoice.import.column.map"
    _description = "Invoice Import Column Mapping"
    _order = "sequence, id"

    wizard_id = fields.Many2one(
        comodel_name="dw.invoice.import.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(default=10)
    col_index = fields.Integer(string="Column Index", default=0)  # 0-based real XLSX column position
    xlsx_column = fields.Char(string="XLSX Column", readonly=True)
    sample_value = fields.Char(string="Sample Value", readonly=True)
    odoo_field = fields.Selection(
        selection=ODOO_FIELD_SELECTION,
        string="Maps To",
        default="skip",
    )
