from odoo import models, fields
from odoo.exceptions import ValidationError
import base64, io
import openpyxl

CREATE_CHUNK_SIZE = 500


class ProductAliasImportWizard(models.TransientModel):
    _name = 'dw.product.alias.import.wizard'
    _description = 'Import Product SKU / Alternate Names'

    file = fields.Binary(required=True)

    @staticmethod
    def _normalize_key(value):
        return str(value).replace('\xa0', ' ').strip().casefold() if value not in (False, None) else False

    def _create_alias_chunk(self, alias_model, vals_list):
        try:
            with self.env.cr.savepoint():
                return len(alias_model.create(vals_list))
        except ValidationError:
            created_count = 0
            for vals in vals_list:
                try:
                    with self.env.cr.savepoint():
                        alias_model.create(vals)
                        created_count += 1
                except ValidationError:
                    continue
            return created_count

    def action_import(self):
        data = base64.b64decode(self.file)
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        sheet = wb.active

        product_model = self.env['product.template']
        alias_model = self.env['dw.product.name.alias']

        # 🔥 preload for performance
        products = {
            self._normalize_key(product['name']): product['id']
            for product in product_model.search_read([], ['name'])
            if product.get('name')
        }

        existing_alias = {
            self._normalize_key(alias['name'])
            for alias in alias_model.search_read([], ['name'])
            if alias.get('name')
        }

        create_vals = []
        imported_count = 0
        skipped_count = 0

        for row in sheet.iter_rows(min_row=2, values_only=True):
            product_name, sku_name = row

            if not product_name or not sku_name:
                skipped_count += 1
                continue

            p_key = self._normalize_key(product_name)
            sku_key = self._normalize_key(sku_name)

            product_id = products.get(p_key)

            # ❌ skip if product not found
            if not product_id:
                skipped_count += 1
                continue

            #  skip duplicate SKU
            if sku_key in existing_alias:
                skipped_count += 1
                continue

            create_vals.append({
                'name': sku_name.strip(),
                'product_tmpl_id': product_id
            })

            existing_alias.add(sku_key)
            if len(create_vals) >= CREATE_CHUNK_SIZE:
                created_count = self._create_alias_chunk(alias_model, create_vals)
                imported_count += created_count
                skipped_count += len(create_vals) - created_count
                create_vals = []

        # 🔥 bulk create (fast)
        if create_vals:
            created_count = self._create_alias_chunk(alias_model, create_vals)
            imported_count += created_count
            skipped_count += len(create_vals) - created_count

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'SKU Import Completed',
                'message': 'Imported %s SKU(s). Skipped %s row(s).' % (imported_count, skipped_count),
                'type': 'success' if imported_count else 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
