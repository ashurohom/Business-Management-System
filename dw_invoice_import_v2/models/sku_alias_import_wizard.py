from odoo import models, fields
import base64, io
import openpyxl


class ProductAliasImportWizard(models.TransientModel):
    _name = 'dw.product.alias.import.wizard'
    _description = 'Import Product SKU / Alternate Names'

    file = fields.Binary(required=True)

    def action_import(self):
        data = base64.b64decode(self.file)
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
        sheet = wb.active

        product_model = self.env['product.template']
        alias_model = self.env['dw.product.name.alias']

        # 🔥 preload for performance
        products = {
            p.name.strip().lower(): p.id
            for p in product_model.search([])
        }

        existing_alias = {
            a.name.strip().lower()
            for a in alias_model.search([])
        }

        create_vals = []

        for row in sheet.iter_rows(min_row=2, values_only=True):
            product_name, sku_name = row

            if not product_name or not sku_name:
                continue

            p_key = str(product_name).strip().lower()
            sku_key = str(sku_name).strip().lower()

            product_id = products.get(p_key)

            # ❌ skip if product not found
            if not product_id:
                continue

            #  skip duplicate SKU
            if sku_key in existing_alias:
                continue

            create_vals.append({
                'name': sku_name.strip(),
                'product_tmpl_id': product_id
            })

            existing_alias.add(sku_key)

        # 🔥 bulk create (fast)
        if create_vals:
            alias_model.create(create_vals)

        return {'type': 'ir.actions.act_window_close'}