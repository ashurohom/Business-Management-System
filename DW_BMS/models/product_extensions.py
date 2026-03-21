import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    detailed_type = fields.Selection(default="product")

    # TEMPORARY: Re-adding field to allow Odoo validation to pass while it strips the old XML views from DB
    min_sale_price = fields.Float(
        string="Minimum Sale Price",
        help="Minimum allowed selling price used for validation or reference.",
    )

    product_storage_location = fields.Char(
        string="Product Locations",
        help="Text field to describe where the product is stored (e.g. Shelf A, Bin 3).",
    )

    opening_stock_ref = fields.Float(
        string="Opening Stock (Reference)",
        help="Reference field for imported opening stock.",
    )

    opening_stock_added_qty = fields.Float(
        string="Opening Stock Added Qty",
        default=0.0,
        readonly=True,
        copy=False,
    )

    opening_stock_pending_qty = fields.Float(
        string="Pending Opening Qty",
        compute="_compute_opening_stock_pending_qty",
        store=True,
    )

    unit_value = fields.Integer(
        string="Unit",
        default=1,
        help="Integer unit value for product.",
    )

    sku = fields.Char(
        string="SKU",
        help="Stock Keeping Unit — a unique identifier for this product (alphanumeric).",
    )

    @api.constrains("name")
    def _check_duplicate_product_name(self):
        for product_tmpl in self:
            product_name = (product_tmpl.name or "").strip()
            if not product_name:
                continue

            duplicate_exists = self.with_context(active_test=False).search_count([
                ("id", "!=", product_tmpl.id),
                ("name", "=ilike", product_name),
            ])
            if duplicate_exists:
                raise ValidationError("Product with this name already exists.")

    @api.depends("opening_stock_ref", "opening_stock_added_qty")
    def _compute_opening_stock_pending_qty(self):
        for product_tmpl in self:
            pending_qty = (
                (product_tmpl.opening_stock_ref or 0.0)
                - (product_tmpl.opening_stock_added_qty or 0.0)
            )
            product_tmpl.opening_stock_pending_qty = max(pending_qty, 0.0)

    # ------------------------------------------------------------------
    # Helper: add opening stock for a single variant via stock.move
    # This is the same mechanism Odoo 17 uses internally for inventory
    # adjustments — guaranteed to update qty_available reliably.
    # ------------------------------------------------------------------
    def _add_opening_stock_move(self, variant, pending_qty, stock_location):
        """Create and validate a stock.move from Inventory Adjustment → WH/Stock."""
        inventory_location = self.env["stock.location"].sudo().search(
            [("usage", "=", "inventory"), ("company_id", "in", [variant.company_id.id, False])],
            limit=1,
        )
        if not inventory_location:
            inventory_location = self.env.ref(
                "stock.location_inventory", raise_if_not_found=False
            )
        if not inventory_location:
            _logger.warning(
                "Inventory loss location missing. Falling back to quant update "
                "for product %s (qty=%s).",
                variant.display_name,
                pending_qty,
            )
            self.env["stock.quant"].sudo().with_company(
                variant.company_id or self.env.company
            )._update_available_quantity(
                variant,
                stock_location,
                pending_qty,
            )
            return

        move = self.env["stock.move"].sudo().create({
            "name": _("Opening Stock: %s", variant.display_name),
            "product_id": variant.id,
            "product_uom_qty": pending_qty,
            "product_uom": variant.uom_id.id,
            "location_id": inventory_location.id,
            "location_dest_id": stock_location.id,
            "company_id": variant.company_id.id or self.env.company.id,
            "is_inventory": True,
        })
        move._action_confirm()
        move.quantity = pending_qty
        move.picked = True
        move._action_done()

    def _get_default_stock_location(self, company):
        """
        Pick a reliable internal stock location for the given company.
        """
        company_id = company.id if company else self.env.company.id
        location = self.env["stock.location"].sudo().search(
            [("usage", "=", "internal"), ("company_id", "in", [company_id, False]), ("active", "=", True)],
            order="company_id desc, id asc",
            limit=1,
        )
        if not location:
            location = self.env.ref("stock.stock_location_stock", raise_if_not_found=False)
        return location

    def _apply_opening_stock_to_template(self, product_tmpl, stock_location=None):
        """Reliable one-shot opening stock apply for a product template."""
        if product_tmpl.detailed_type != "product":
            return False
        variant = product_tmpl.product_variant_id
        if not variant:
            return False

        qty = product_tmpl.opening_stock_ref or 0.0
        if (
            float_compare(
                qty,
                0.0,
                precision_rounding=product_tmpl.uom_id.rounding,
            )
            <= 0
        ):
            return False

        target_company = variant.company_id or self.env.company
        target_stock_location = stock_location or self._get_default_stock_location(target_company)
        if not target_stock_location:
            raise UserError(_("Default stock location not found for company %s.") % (target_company.display_name,))

        # Use the same stock.move flow that updates on-hand reliably.
        self._add_opening_stock_move(variant, qty, target_stock_location)
        product_tmpl.sudo().write({
            "opening_stock_added_qty": (product_tmpl.opening_stock_added_qty or 0.0) + qty,
            "opening_stock_ref": 0.0,
        })
        return True

    # ------------------------------------------------------------------
    # Single-product button  (smart button on product form)
    # ------------------------------------------------------------------
    def action_add_products_stock(self):
        """Add pending opening stock for the current product (single record)."""
        updated_count = 0

        for product_tmpl in self:
            if (product_tmpl.opening_stock_ref or 0.0) <= 0:
                continue

            # Skip non-storable products
            if product_tmpl.detailed_type != "product":
                continue

            if self._apply_opening_stock_to_template(product_tmpl):
                updated_count += 1

        message = _("Opening stock added for %s product(s).", updated_count)
        if not updated_count:
            message = _("No pending opening stock found.")

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Add Products"),
                "message": message,
                "type": "success" if updated_count else "warning",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Server-action entry point  (menu item — no selection needed)
    # ------------------------------------------------------------------
    @api.model
    def action_add_all_pending_to_stock(self):
        """
        Called from ir.actions.server / menu.
        Searches by RAW stored fields, filters in Python.
        """
        pending = self.env["product.template"].sudo().search([
            ("detailed_type", "=", "product"),
            ("opening_stock_ref", ">", 0),
        ])

        if not pending:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Add All To Stock"),
                    "message": _("No pending opening stock found."),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return pending.action_add_all_to_stock()

    # ------------------------------------------------------------------
    # Batch method  (operates on self — called by the method above)
    # ------------------------------------------------------------------
    def action_add_all_to_stock(self):
        """
        Batch-process all products in self.
        Uses stock.move (Inventory → Stock) — the same mechanism 
        uses internally for inventory adjustments.
        """
        if not self:
            raise UserError(_("No products selected."))

        updated_count = 0
        skipped_no_variant = []
        skipped_already_done = []
        skipped_non_storable = []

        for product_tmpl in self:
            if (product_tmpl.opening_stock_ref or 0.0) <= 0:
                skipped_already_done.append(product_tmpl.name)
                continue

            if product_tmpl.detailed_type != "product":
                skipped_non_storable.append(
                    f"{product_tmpl.name} ({product_tmpl.detailed_type})"
                )
                continue

            variant = product_tmpl.product_variant_id
            if not variant:
                skipped_no_variant.append(product_tmpl.name)
                continue

            if self._apply_opening_stock_to_template(product_tmpl):
                updated_count += 1

        # ---- Build feedback message ----
        lines = []
        if updated_count:
            lines.append(_(" Stock added for %s product(s).", updated_count))
        if skipped_non_storable:
            lines.append(
                _(" Skipped (not Storable type) — %s: %s",
                  len(skipped_non_storable), ", ".join(skipped_non_storable))
            )
        if skipped_already_done:
            lines.append(
                _("⏭ Already processed (%s): %s", len(skipped_already_done),
                  ", ".join(skipped_already_done))
            )
        if skipped_no_variant:
            lines.append(
                _(" No variant found, skipped (%s): %s",
                  len(skipped_no_variant), ", ".join(skipped_no_variant))
            )

        if not updated_count and not lines:
            lines.append(_("No pending opening stock found."))

        message = " | ".join(lines)
        notif_type = "success" if updated_count else "warning"

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Add All To Stock"),
                "message": message,
                "type": notif_type,
                "sticky": True,
            },
        }
