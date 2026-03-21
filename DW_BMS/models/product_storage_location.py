# -*- coding: utf-8 -*-
from odoo import api, fields, models


class DwProductStorageLocation(models.Model):
    _name = "dw.product.storage.location"
    _description = "Product Storage Location"
    _order = "name"

    name = fields.Char(required=True, index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "dw_product_storage_location_name_uniq",
            "unique(name)",
            "This product location already exists.",
        )
    ]


class ProductTemplate(models.Model):
    _inherit = "product.template"

    product_storage_location_id = fields.Many2one(
        comodel_name="dw.product.storage.location",
        string="Product Locations",
        help="Select an existing location or create a new one. The value is stored in Product Locations text field.",
    )

    @api.model
    def _find_or_create_storage_location(self, raw_name):
        name = (raw_name or "").strip()
        if not name:
            return self.env["dw.product.storage.location"]
        location = self.env["dw.product.storage.location"].sudo().search(
            [("name", "=ilike", name)], limit=1
        )
        if location:
            return location
        return self.env["dw.product.storage.location"].sudo().create({"name": name})

    @api.model_create_multi
    def create(self, vals_list):
        location_model = self.env["dw.product.storage.location"].sudo()
        for vals in vals_list:
            if vals.get("product_storage_location_id") and not vals.get("product_storage_location"):
                location = location_model.browse(vals["product_storage_location_id"])
                vals["product_storage_location"] = (location.name or "").strip()

        records = super().create(vals_list)

        for record in records:
            if record.product_storage_location:
                location = self._find_or_create_storage_location(record.product_storage_location)
                if location and record.product_storage_location_id != location:
                    record.with_context(skip_location_sync=True).sudo().write(
                        {"product_storage_location_id": location.id}
                    )
        return records

    def write(self, vals):
        if self.env.context.get("skip_location_sync"):
            return super().write(vals)

        location_model = self.env["dw.product.storage.location"].sudo()
        write_vals = dict(vals)

        if "product_storage_location_id" in write_vals and "product_storage_location" not in write_vals:
            location_id = write_vals.get("product_storage_location_id")
            if location_id:
                location = location_model.browse(location_id)
                write_vals["product_storage_location"] = (location.name or "").strip()
            else:
                write_vals["product_storage_location"] = False

        result = super().write(write_vals)

        if "product_storage_location" in write_vals:
            for record in self:
                if record.product_storage_location:
                    location = self._find_or_create_storage_location(record.product_storage_location)
                    if location and record.product_storage_location_id != location:
                        record.with_context(skip_location_sync=True).sudo().write(
                            {"product_storage_location_id": location.id}
                        )
                elif record.product_storage_location_id:
                    record.with_context(skip_location_sync=True).sudo().write(
                        {"product_storage_location_id": False}
                    )

        return result
