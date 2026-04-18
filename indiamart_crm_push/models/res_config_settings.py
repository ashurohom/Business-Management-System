from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    indiamart_webhook_token = fields.Char(
        string="IndiaMART Webhook Token",
        config_parameter='indiamart_crm_push.webhook_token'
    )

    indiamart_default_team_id = fields.Many2one(
        'crm.team',
        string="Default CRM Team",
        config_parameter='indiamart_crm_push.default_team_id'
    )

    indiamart_default_user_id = fields.Many2one(
        'res.users',
        string="Default Salesperson",
        config_parameter='indiamart_crm_push.default_user_id'
    )