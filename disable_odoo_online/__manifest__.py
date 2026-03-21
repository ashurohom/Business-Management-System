{
    "name": "Remove odoo.com Bindings",
    "version": "17.0.1.0.0",
    "author": "Dreamwarez",
    "website": "",
    "license": "AGPL-3",
    "category": "Hidden",
    "depends": ["mail"],
    "data": ["views/ir_ui_menu.xml"],
    "assets": {
        "web.assets_backend": [
            "disable_odoo_online/static/src/js/user_menu_items.esm.js"
        ],
    },
    "installable": True,
    "post_init_hook": "post_init_hook",
}
