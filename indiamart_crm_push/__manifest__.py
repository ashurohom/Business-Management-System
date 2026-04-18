{
    'name': 'IndiaMART CRM Push Integration',
    'version': '17.0.1.0.0',
    'summary': 'Receive IndiaMART leads in Odoo CRM through webhook',
    'category': 'CRM',
    'author': 'Custom',
    'license': 'LGPL-3',
    'depends': ['crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/crm_lead_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'installable': True,
    'application': False,
}