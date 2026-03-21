{
    'name': 'Custom Branding',
    'version': '17.0.1.0.0',
    'author': 'Dreamwarez',
    'website': 'https://dreamwarez.com',
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': ['static/src/xml/custom_template.xml',
             'views/custom_favicon.xml',
             'views/login_title.xml',
             ],
    
    'assets': {
        'web.assets_backend': [
            "custom_branding/static/src/js/early_title_fix.js",
            'custom_branding/static/src/js/custom_title.js',
            'custom_branding/static/src/js/hide_mail_odoo_title.js',
            # 'custom_branding/static/src/js/custom_content.js',
        ],
    },      
    'installable': True,
    'auto_install': False,
}