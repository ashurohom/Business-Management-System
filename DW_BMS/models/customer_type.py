from odoo import models, fields


class CustomerType(models.Model):
    _name = "dw.customer.type"
    _description = "Customer Type"
    _order = "name"

    name = fields.Char(string="Name", required=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("dw_customer_type_name_unique", "unique(name)", "Customer Type already exists."),
    ]
