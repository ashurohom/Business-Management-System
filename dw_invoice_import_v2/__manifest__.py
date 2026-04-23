
{
    'name': 'DW Invoice Import V2',
    'version': '2.0',
    'depends': ['account', 'product', 'sale', 'stock', 'DW_BMS'],
    'data': [
        'security/ir.model.access.csv',
        'views/import_wizard_view.xml',
        'views/sku_alias_import_wizard.xml',
    ],
    'installable': True
}
