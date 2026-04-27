from odoo import http
from odoo.http import request
import json 

class DWBMSAPI(http.Controller):

    @http.route('/api/test', type='json', auth='public', methods=['GET'], csrf=False)
    def test_api(self, **kwargs):
        return {
            "status": "success",
            "message": "API is working in Odoo 17"
        }


    @http.route('/api/customers', type='http', auth='public', methods=['POST'], csrf=False)
    def get_customers(self, **kwargs):
        partners = request.env['res.partner'].sudo().search([])

        data = []
        for p in partners:
            data.append({
                "name": p.name,
                "email": p.email,
                "phone": p.phone
            })

        return request.make_response(
            json.dumps({
                "status": "success",
                "data": data
            }),
            headers=[('Content-Type', 'application/json')]
        )  


    @http.route('/api/invoices', type='http', auth='public', methods=['POST'], csrf=False)
    def get_invoices(self, **kwargs):

        invoices = request.env['account.move'].sudo().search([
            ('move_type', '=', 'out_invoice')
        ])

        data = []
        for inv in invoices:
            data.append({
                "invoice_number": inv.name,
                "customer": inv.partner_id.name,
                "invoice_date": str(inv.invoice_date),
                "total_amount": inv.amount_total,
                "payment_status": inv.payment_state
            })

        return request.make_response(
            json.dumps({
                "status": "success",
                "count": len(data),
                "data": data
            }),
            headers=[('Content-Type', 'application/json')]
        )    