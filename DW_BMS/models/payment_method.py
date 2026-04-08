from odoo import fields, models


CUSTOM_PAYMENT_METHOD_SELECTION = [
    ("cash", "Cash"),
    ("card", "Card"),
    ("cheque", "Cheque"),
    ("bank", "Bank Transfer"),
    ("other", "Other"),
]


class AccountPayment(models.Model):
    _inherit = "account.payment"

    custom_payment_method = fields.Selection(
        selection=CUSTOM_PAYMENT_METHOD_SELECTION,
        string="Custom Payment Method",
    )


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    custom_payment_method = fields.Selection(
        selection=CUSTOM_PAYMENT_METHOD_SELECTION,
        string="Custom Payment Method",
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals["custom_payment_method"] = self.custom_payment_method
        return vals
