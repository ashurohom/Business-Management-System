
{
    'name': 'DW Job Work',
    'version': '2.0',
    'license': 'LGPL-3',
    'depends': ['stock','product'],
    'data': [
        'security/job_work_security.xml',
        'security/ir.model.access.csv',
        'data/location.xml',
        'views/issue_views.xml',
        'views/receipt_views.xml',
        'views/dashboard_views.xml',
        'reports/job_work_issue_report.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
}
