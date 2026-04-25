{
    'name': 'Indian e-Invoice / e-Way Bill JSON Export',
    'version': '17.0.1.0.0',
    'summary': 'Generate Indian government schema style JSON for e-Invoice and e-Way Bill from invoices',
    'category': 'Accounting',
    'author': 'OpenAI',
    'license': 'LGPL-3',
    'depends': ['account','l10n_in_edi_ewaybill'],
    'data': [
        'security/ir.model.access.csv',
        'views/invoice_json_wizard_views.xml',
        'views/account_move_views.xml',
    ],
    'installable': True,
    'application': False,
}
