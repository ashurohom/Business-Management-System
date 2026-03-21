from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression
from odoo.tools import ustr


class ProductNameAlias(models.Model):
    _name = "dw.product.name.alias"
    _description = "Product Alternate Name"
    _order = "name"

    name = fields.Char(string="Alternate Name", required=True, index=True)
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product",
        required=True,
        ondelete="cascade",
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name"):
                vals["name"] = vals["name"].strip()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("name"):
            vals["name"] = vals["name"].strip()
        return super().write(vals)

    @api.constrains("name")
    def _check_unique_name_case_insensitive(self):
        for alias in self:
            if not alias.name:
                continue
            normalized_name = alias.name.strip()
            duplicate = self.search(
                [("id", "!=", alias.id), ("name", "=ilike", normalized_name)],
                limit=1,
            )
            if duplicate:
                raise ValidationError("Alternate name must be unique across products.")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    alias_ids = fields.One2many(
        "dw.product.name.alias",
        "product_tmpl_id",
        string="Alternate Names",
        copy=True,
    )

    def _check_sales_price_edit_access(self, vals, for_create=False):
        if "list_price" not in vals:
            return
        if self.env.su or self.env.user.has_group("DW_BMS.group_bms_admin"):
            return
        if for_create and self.env.user.has_group("DW_BMS.group_bms_sales"):
            return
        raise ValidationError("Only BMS Admin can change Product Sales Price.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_sales_price_edit_access(vals, for_create=True)
        return super().create(vals_list)

    @api.model
    def load(self, fields, data):
        """Normalize rows and collapse same-name product imports into one template."""

        def _norm_text(value):
            if value is None:
                return ""
            return ustr(value).strip()

        def _is_empty(value):
            if value is None:
                return True
            if isinstance(value, str):
                return not value.strip()
            return False

        field_pos = {name: idx for idx, name in enumerate(fields)}
        cost_idx = field_pos.get("standard_price")
        name_idx = field_pos.get("name")
        sku_idx = field_pos.get("default_code")

        normalized_rows = []
        for row in data:
            new_row = list(row)
            if cost_idx is not None and cost_idx < len(new_row):
                value = new_row[cost_idx]
                if value is None:
                    new_row[cost_idx] = ""
                elif isinstance(value, str) and value.strip().lower() in {"none", "null"}:
                    new_row[cost_idx] = ""
            normalized_rows.append(new_row)

        if name_idx is None or sku_idx is None:
            return super().load(fields, normalized_rows)

        merged_rows = []
        row_index_by_name = {}
        skus_by_name = {}

        for row in normalized_rows:
            product_name = _norm_text(row[name_idx] if name_idx < len(row) else "")
            sku_name = _norm_text(row[sku_idx] if sku_idx < len(row) else "")

            if not product_name:
                merged_rows.append(row)
                continue

            name_key = product_name.casefold()
            if name_key not in row_index_by_name:
                row_index_by_name[name_key] = len(merged_rows)
                merged_rows.append(row)
            else:
                base_row = merged_rows[row_index_by_name[name_key]]
                for idx, value in enumerate(row):
                    if idx >= len(base_row):
                        continue
                    if _is_empty(base_row[idx]) and not _is_empty(value):
                        base_row[idx] = value

            if sku_name:
                skus_by_name.setdefault(name_key, set()).add(sku_name)

        result = super().load(fields, merged_rows)

        imported_ids = result.get("ids") or []
        product_by_name = {}
        for idx, row in enumerate(merged_rows):
            product_name = _norm_text(row[name_idx] if name_idx < len(row) else "")
            if not product_name:
                continue
            name_key = product_name.casefold()
            if name_key in product_by_name:
                continue

            product = False
            if idx < len(imported_ids) and imported_ids[idx]:
                product = self.browse(imported_ids[idx]).exists()
            if not product:
                product = self.search([("name", "=ilike", product_name)], order="id desc", limit=1)
            if product:
                product_by_name[name_key] = product

        alias_model = self.env["dw.product.name.alias"]
        for name_key, sku_names in skus_by_name.items():
            product = product_by_name.get(name_key)
            if not product:
                continue

            existing_aliases = {
                (alias.name or "").strip().casefold()
                for alias in product.alias_ids
                if alias.name
            }
            for sku_name in sorted(sku_names):
                sku_key = sku_name.casefold()
                if sku_key in existing_aliases:
                    continue

                conflict = alias_model.search([("name", "=ilike", sku_name)], limit=1)
                if conflict and conflict.product_tmpl_id.id != product.id:
                    raise ValidationError(
                        "Alternate SKU '%s' already exists for product '%s'."
                        % (sku_name, conflict.product_tmpl_id.display_name)
                    )

                alias_model.create({
                    "name": sku_name,
                    "product_tmpl_id": product.id,
                })
                existing_aliases.add(sku_key)

        return result

    def write(self, vals):
        self._check_sales_price_edit_access(vals)
        return super().write(vals)

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=None, order=None):
        domain = domain or []
        ids = super()._name_search(name=name, domain=domain, operator=operator, limit=limit, order=order)
        if not name:
            return ids

        alias_templates = self.env["dw.product.name.alias"].search([("name", operator, name)]).mapped("product_tmpl_id")
        if not alias_templates:
            return ids

        existing_ids = list(ids)
        remaining = (limit - len(existing_ids)) if limit else None
        if limit and remaining <= 0:
            return existing_ids

        extra_domain = expression.AND([
            domain,
            [("id", "in", alias_templates.ids), ("id", "not in", existing_ids)],
        ])
        extra_ids = self._search(extra_domain, limit=remaining, order=order)
        return existing_ids + list(extra_ids)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _check_sales_price_edit_access(self, vals, for_create=False):
        if "list_price" not in vals:
            return
        if self.env.su or self.env.user.has_group("DW_BMS.group_bms_admin"):
            return
        if for_create and self.env.user.has_group("DW_BMS.group_bms_sales"):
            return
        raise ValidationError("Only BMS Admin can change Product Sales Price.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_sales_price_edit_access(vals, for_create=True)
        return super().create(vals_list)

    @api.model
    def load(self, fields, data):
        """Normalize imported cost values so empty Excel cells do not crash float parsing."""
        if "standard_price" not in fields:
            return super().load(fields, data)

        cost_idx = fields.index("standard_price")
        normalized_data = []
        for row in data:
            new_row = list(row)
            if cost_idx < len(new_row):
                value = new_row[cost_idx]
                if value is None:
                    new_row[cost_idx] = ""
                elif isinstance(value, str) and value.strip().lower() in {"none", "null"}:
                    new_row[cost_idx] = ""
            normalized_data.append(new_row)
        return super().load(fields, normalized_data)

    def write(self, vals):
        self._check_sales_price_edit_access(vals)
        return super().write(vals)

    @api.model
    def _name_search(self, name="", domain=None, operator="ilike", limit=None, order=None):
        domain = domain or []
        ids = super()._name_search(name=name, domain=domain, operator=operator, limit=limit, order=order)
        if not name:
            return ids

        alias_templates = self.env["dw.product.name.alias"].search([("name", operator, name)]).mapped("product_tmpl_id")
        if not alias_templates:
            return ids

        existing_ids = list(ids)
        remaining = (limit - len(existing_ids)) if limit else None
        if limit and remaining <= 0:
            return existing_ids

        extra_domain = expression.AND([
            domain,
            [("product_tmpl_id", "in", alias_templates.ids), ("id", "not in", existing_ids)],
        ])
        extra_ids = self._search(extra_domain, limit=remaining, order=order)
        return existing_ids + list(extra_ids)
