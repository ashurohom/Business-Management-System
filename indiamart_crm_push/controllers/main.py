import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class IndiaMartWebhookController(http.Controller):

    @http.route(
        '/api/indiamart/webhook',
        type='http',
        auth='public',
        methods=['POST'],
        csrf=False
    )
    def indiamart_webhook(self, **kwargs):
        """
        IndiaMART webhook endpoint.

        IndiaMART may send data as:
        - form-data / x-www-form-urlencoded
        - raw JSON

        This endpoint supports both.
        """
        try:
            data = self._extract_payload()
            _logger.info("IndiaMART webhook payload received: %s", data)

            if not data:
                return request.make_json_response({
                    'success': False,
                    'message': 'No payload received'
                }, status=400)

            # Optional token validation
            saved_token = request.env['ir.config_parameter'].sudo().get_param(
                'indiamart_crm_push.webhook_token'
            )
            received_token = (
                data.get('token')
                or request.httprequest.headers.get('X-Webhook-Token')
                or request.httprequest.headers.get('x-webhook-token')
            )

            if saved_token and received_token != saved_token:
                _logger.warning(
                    "IndiaMART webhook unauthorized. Received token: %s", received_token
                )
                return request.make_json_response({
                    'success': False,
                    'message': 'Unauthorized'
                }, status=401)

            query_id = (
                data.get('UNIQUE_QUERY_ID')
                or data.get('unique_query_id')
                or data.get('QueryID')
                or data.get('query_id')
            )

            lead_obj = request.env['crm.lead'].sudo()

            if query_id:
                existing_lead = lead_obj.search(
                    [('x_indiamart_query_id', '=', query_id)],
                    limit=1
                )
                if existing_lead:
                    _logger.info("Duplicate IndiaMART lead skipped. Query ID: %s", query_id)
                    return request.make_json_response({
                        'success': True,
                        'message': 'Duplicate lead skipped',
                        'lead_id': existing_lead.id
                    }, status=200)

            vals = self._prepare_lead_vals(data)
            lead = lead_obj.create(vals)

            _logger.info("IndiaMART lead created successfully. Lead ID: %s", lead.id)

            return request.make_json_response({
                'success': True,
                'message': 'Lead created successfully',
                'lead_id': lead.id
            }, status=200)

        except Exception as e:
            _logger.exception("Error while processing IndiaMART webhook: %s", e)
            return request.make_json_response({
                'success': False,
                'message': str(e)
            }, status=500)

    def _extract_payload(self):
        """Extract payload from JSON body or POST form fields."""
        httprequest = request.httprequest

        data = {}

        # 1. Try raw JSON
        raw_data = httprequest.data
        if raw_data:
            try:
                decoded = raw_data.decode('utf-8')
                json_data = json.loads(decoded)
                if isinstance(json_data, dict):
                    data.update(json_data)
            except Exception:
                pass

        # 2. Try form fields
        if httprequest.form:
            data.update(httprequest.form.to_dict())

        # 3. Fallback kwargs
        if not data:
            data.update(request.params or {})

        return data

    def _prepare_lead_vals(self, data):
        icp = request.env['ir.config_parameter'].sudo()

        default_team_id = icp.get_param('indiamart_crm_push.default_team_id')
        default_user_id = icp.get_param('indiamart_crm_push.default_user_id')

        query_id = (
            data.get('UNIQUE_QUERY_ID')
            or data.get('unique_query_id')
            or data.get('QueryID')
            or data.get('query_id')
        )

        customer_name = (
            data.get('SENDER_NAME')
            or data.get('sender_name')
            or data.get('NAME')
            or data.get('name')
            or ''
        )

        mobile = (
            data.get('SENDER_MOBILE')
            or data.get('sender_mobile')
            or data.get('MOBILE')
            or data.get('mobile')
            or ''
        )

        email = (
            data.get('SENDER_EMAIL')
            or data.get('sender_email')
            or data.get('EMAIL')
            or data.get('email')
            or ''
        )

        subject = (
            data.get('SUBJECT')
            or data.get('subject')
            or data.get('QUERY_PRODUCT_NAME')
            or data.get('query_product_name')
            or 'IndiaMART Lead'
        )

        message = (
            data.get('ENQUIRY_MESSAGE')
            or data.get('enquiry_message')
            or data.get('MESSAGE')
            or data.get('message')
            or ''
        )

        city = (
            data.get('SENDER_CITY')
            or data.get('sender_city')
            or data.get('CITY')
            or data.get('city')
            or ''
        )

        company = (
            data.get('SENDER_COMPANY')
            or data.get('sender_company')
            or data.get('COMPANY')
            or data.get('company')
            or ''
        )

        vals = {
            'name': subject,
            'partner_name': customer_name or company or 'IndiaMART Customer',
            'contact_name': customer_name or False,
            'phone': mobile,
            'mobile': mobile,
            'email_from': email,
            'city': city,
            'description': message,
            'type': 'lead',
            'x_indiamart_query_id': query_id,
            'x_indiamart_source': 'IndiaMART Push API',
            'x_indiamart_raw_data': json.dumps(data, ensure_ascii=False, indent=2),
        }

        if default_team_id:
            try:
                vals['team_id'] = int(default_team_id)
            except Exception:
                pass

        if default_user_id:
            try:
                vals['user_id'] = int(default_user_id)
            except Exception:
                pass

        return vals