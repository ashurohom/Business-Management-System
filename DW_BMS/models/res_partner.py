from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = "res.partner"

    supplier_type = fields.Selection(
        [
            ('individual', 'Individual'),
            ('business', 'Business'),
        ],
        string="Supplier Type",
        default='individual'
    )

    # NEW FIELD ADDED (SAFE)
    customer_type = fields.Selection(
        [
            ('wholesaler', 'Wholesaler'),
            ('retailer', 'Retailer'),
            ('end_user', 'End User'),
        ],
        string="Customer Type"
    )
    customer_type_master_id = fields.Many2one(
        "dw.customer.type",
        string="Customer Type (Master)",
        ondelete="set null",
    )

    # ------------------------------------------------
    # Mobile validation only within the same customer
    # ------------------------------------------------
    @api.constrains('phone', 'mobile')
    def _check_unique_phone_mobile(self):
        for partner in self:
            if partner.phone and partner.mobile and partner.phone == partner.mobile:
                raise ValidationError(
                    "Mobile 1 and Mobile 2 cannot be the same number."
                )

    @api.constrains('name')
    def _check_duplicate_partner_name(self):
        for partner in self:
            partner_name = (partner.name or "").strip()
            if not partner_name:
                continue

            duplicate_exists = self.with_context(active_test=False).search_count([
                ("id", "!=", partner.id),
                ("name", "=ilike", partner_name),
            ])
            if duplicate_exists:
                raise ValidationError("Contact with this name already exists.")

    # -----------------------------------
    # GST REQUIRED FOR BUSINESS SUPPLIER
    # -----------------------------------
    @api.constrains('supplier_type', 'vat', 'supplier_rank')
    def _check_gst_for_business_supplier(self):
        for partner in self:
            if partner.supplier_rank > 0 and partner.supplier_type == 'business':
                if not partner.vat:
                    raise ValidationError(
                        "GST Number (Tax ID) is mandatory for Business Suppliers."
                    )




class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    hsn_code = fields.Char(
        string="HSN",
        related="product_id.l10n_in_hsn_code",
        store=True
    )



class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    hsn_code = fields.Char(
        string="HSN",
        related="product_id.l10n_in_hsn_code",
        store=True
    )
