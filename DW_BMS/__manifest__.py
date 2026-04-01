{
    "name": "DW BMS",
    "version": "1.0",
    "category": "Operations",
    "summary": "DW - Business Management System",
    "author": "Dreamwarez",
    "depends": [
        "base",
        "base_import",
        "base_accounting_kit",
        "contacts",
        "sale_management",
        "purchase",
        "account",
        "product",
        "stock",
        "mrp",
        "hr",
        "l10n_in",
    ],
    "data": [
        "security/security.xml",
        "security/hide_bms_reports_groups.xml",
        "security/dispatch_team_group.xml",
        "security/sales_team_group.xml",
        "security/packing_team_group.xml",
        "security/dispatch_team_restrictions.xml",
        "security/record_rules.xml",
        "security/ir.model.access.csv",

        # Sequence data
        "data/invoice_import_sequence.xml",
        "data/customer_type_data.xml",
        "data/purchase_status_cron.xml",

        # Reports
        "reports/report_common_templates.xml",
        "reports/sale_quotation_custom_report.xml",
        "reports/invoice_custom_report.xml",

        # Core views
        "views/res_partner_view.xml",
        "views/customer_type_view.xml",
        "views/product_alias_view.xml",
        "views/account_move_view.xml",
        "views/sale_order_view.xml",
        "views/product_alert_views.xml",
        "views/product_storage_location_views.xml",
        "views/product_extensions_view.xml",
        "views/stock_picking_view.xml",

        # Invoice Import feature
        "views/invoice_import_wizard_view.xml",
        "views/invoice_import_log_view.xml",
        "views/invoice_import_menu.xml",
        "views/invoice_numbers.xml",
        "reports/packing_order_report.xml",
        "views/packing_order_views.xml",
        "views/sale_order_packing_views.xml",
        "views/shipping_management_views.xml",
        "views/activity_timeline_views.xml",

        # Wizard & reports
        "wizard/bms_report_wizard_view.xml",
        "views/account_partner_ledger_view.xml",
        "reports/bms_report_templates.xml",
    ],
    "installable": True,
    "application": True,
}
