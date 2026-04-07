from odoo import _, api, models
from odoo.exceptions import ValidationError


class MrpBom(models.Model):
    _inherit = "mrp.bom"

    def _get_duplicate_bom_domain(self):
        self.ensure_one()
        if not self.product_tmpl_id:
            return []
        return [
            ("product_tmpl_id", "=", self.product_tmpl_id.id),
            ("id", "!=", self.id),
        ]

    def _raise_duplicate_bom_error(self):
        self.ensure_one()
        raise ValidationError(
            _("A BoM already exists for product: %s") % self.product_tmpl_id.display_name
        )

    def _check_duplicate_bom_per_product(self):
        for bom in self:
            domain = bom._get_duplicate_bom_domain()
            if domain and self.with_context(active_test=False).search_count(domain):
                bom._raise_duplicate_bom_error()

    @api.constrains("product_tmpl_id")
    def _constrain_duplicate_bom_per_product(self):
        self._check_duplicate_bom_per_product()

    @api.model_create_multi
    def create(self, vals_list):
        boms = super().create(vals_list)
        boms._check_duplicate_bom_per_product()
        return boms

    def copy(self, default=None):
        self.ensure_one()
        default = dict(default or {})
        product_tmpl = self.env["product.template"].browse(
            default.get("product_tmpl_id", self.product_tmpl_id.id)
        )
        if product_tmpl and self.with_context(active_test=False).search_count([
            ("product_tmpl_id", "=", product_tmpl.id),
        ]):
            raise ValidationError(
                _("A BoM already exists for product: %s") % product_tmpl.display_name
            )
        return super().copy(default)
