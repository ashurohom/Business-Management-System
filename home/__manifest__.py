{
    "name": "Home",
    "version": "17.0.1.0.0",
    "summary": "Home Screen Dashboard for BMS",
    "author": "Dreamwarez",
    "category": "Operations",
    "depends": [
        "base",
        "sale",
        "purchase",
        "account",
        "stock",
        "mrp",
        "DW_BMS"
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/home_dashboard_view.xml",
        "views/home_menu.xml"
    ],
    "installable": True,
    "application": True
}
