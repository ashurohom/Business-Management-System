from odoo import api, fields, models


class PackingDispatchMode(models.Model):
    _name = "packing.dispatch.mode"
    _description = "Packing Dispatch Mode"
    _order = "name"

    name = fields.Char(required=True)


class PackingCourierCompany(models.Model):
    _name = "packing.courier.company"
    _description = "Packing Courier Company"
    _order = "name"

    name = fields.Char(required=True)


class PackingOrder(models.Model):
    _name = "packing.order"
    _description = "Packing Order"
    _rec_name = "invoice_id"
    _order = "id desc"

    invoice_id = fields.Many2one("account.move", string="Invoice", required=True, ondelete="cascade")
    from_partner_id = fields.Many2one("res.partner", string="From Partner", compute="_compute_addresses", store=True)
    from_name = fields.Char(string="From Name", compute="_compute_addresses", store=True)
    from_address = fields.Text(string="From Address", compute="_compute_addresses", store=True)
    from_mobile = fields.Char(string="From Mobile", compute="_compute_addresses", store=True)
    from_city = fields.Char(string="From City", compute="_compute_addresses", store=True)
    from_state = fields.Char(string="From State", compute="_compute_addresses", store=True)
    from_country = fields.Char(string="From Country", compute="_compute_addresses", store=True)
    from_pincode = fields.Char(string="From Pincode", compute="_compute_addresses", store=True)
    to_partner_id = fields.Many2one("res.partner", string="To Partner", compute="_compute_addresses", store=True)
    to_name = fields.Char(string="To Name", compute="_compute_addresses", store=True)
    to_address = fields.Text(string="To Address", compute="_compute_addresses", store=True)
    to_mobile = fields.Char(string="To Mobile", compute="_compute_addresses", store=True)
    to_city = fields.Char(string="To City", compute="_compute_addresses", store=True)
    to_state = fields.Char(string="To State", compute="_compute_addresses", store=True)
    to_country = fields.Char(string="To Country", compute="_compute_addresses", store=True)
    to_pincode = fields.Char(string="To Pincode", compute="_compute_addresses", store=True)
    dispatch_mode_id = fields.Many2one("packing.dispatch.mode", string="Dispatch Mode")
    courier_company_id = fields.Many2one("packing.courier.company", string="Courier Company")
    packing_line_ids = fields.One2many("packing.order.line", "packing_id", string="Packing Lines", copy=True)

    def action_print_packing_slip(self):
        self.ensure_one()
        return self.env.ref("DW_BMS.action_report_packing_order").report_action(self)

    @api.depends(
        "invoice_id",
        "invoice_id.delivery_type",
        "invoice_id.partner_id",
        "invoice_id.partner_id.name",
        "invoice_id.billing_partner_id",
        "invoice_id.billing_partner_id.name",
        "invoice_id.shipping_partner_id",
        "invoice_id.shipping_partner_id.name",
        "invoice_id.billing_customer_name",
        "invoice_id.bill_to_address",
        "invoice_id.bill_to_city",
        "invoice_id.bill_to_state_id",
        "invoice_id.bill_to_country",
        "invoice_id.bill_to_zip",
        "invoice_id.billing_address",
        "invoice_id.billing_mobile",
        "invoice_id.shipping_customer_name",
        "invoice_id.ship_to_address",
        "invoice_id.ship_to_city",
        "invoice_id.ship_to_state_id",
        "invoice_id.ship_to_country",
        "invoice_id.ship_to_zip",
        "invoice_id.shipping_address",
        "invoice_id.shipping_mobile",
        "invoice_id.company_id",
        "invoice_id.company_id.name",
        "invoice_id.company_id.phone",
        "invoice_id.company_id.partner_id",
        "invoice_id.company_id.partner_id.name",
        "invoice_id.company_id.partner_id.street",
        "invoice_id.company_id.partner_id.street2",
        "invoice_id.company_id.partner_id.city",
        "invoice_id.company_id.partner_id.state_id",
        "invoice_id.company_id.partner_id.zip",
        "invoice_id.company_id.partner_id.country_id",
        "invoice_id.company_id.partner_id.phone",
        "invoice_id.company_id.partner_id.mobile",
    )
    def _compute_addresses(self):
        for rec in self:
            rec.update({
                "from_partner_id": False,
                "from_name": False,
                "from_address": False,
                "from_mobile": False,
                "from_city": False,
                "from_state": False,
                "from_country": False,
                "from_pincode": False,
                "to_partner_id": False,
                "to_name": False,
                "to_address": False,
                "to_mobile": False,
                "to_city": False,
                "to_state": False,
                "to_country": False,
                "to_pincode": False,
            })
            if not rec.invoice_id:
                continue

            invoice = rec.invoice_id
            company_partner = invoice.company_id.partner_id
            billing_partner = invoice.billing_partner_id or invoice.partner_id
            shipping_partner = invoice.shipping_partner_id or invoice.partner_id

            company_vals = rec._prepare_company_address_vals(invoice)
            billing_vals = rec._prepare_invoice_address_vals(
                partner=billing_partner,
                name=invoice.billing_customer_name,
                mobile=invoice.billing_mobile,
                address=invoice.bill_to_address,
                city=invoice.bill_to_city,
                state=invoice.bill_to_state_id.name if invoice.bill_to_state_id else False,
                country=invoice.bill_to_country,
                pincode=invoice.bill_to_zip,
            )
            shipping_vals = rec._prepare_invoice_address_vals(
                partner=shipping_partner,
                name=invoice.shipping_customer_name,
                mobile=invoice.shipping_mobile,
                address=invoice.ship_to_address,
                city=invoice.ship_to_city,
                state=invoice.ship_to_state_id.name if invoice.ship_to_state_id else False,
                country=invoice.ship_to_country,
                pincode=invoice.ship_to_zip,
            )

            if invoice.delivery_type == "third_party_delivery":
                from_vals = billing_vals
                to_vals = shipping_vals
            elif invoice.delivery_type == "ship_to_different":
                from_vals = company_vals
                to_vals = shipping_vals
            else:
                from_vals = company_vals
                to_vals = billing_vals

            rec.update({
                "from_partner_id": from_vals["partner_id"],
                "from_name": from_vals["name"],
                "from_address": from_vals["address"],
                "from_mobile": from_vals["mobile"],
                "from_city": from_vals["city"],
                "from_state": from_vals["state"],
                "from_country": from_vals["country"],
                "from_pincode": from_vals["pincode"],
                "to_partner_id": to_vals["partner_id"],
                "to_name": to_vals["name"],
                "to_address": to_vals["address"],
                "to_mobile": to_vals["mobile"],
                "to_city": to_vals["city"],
                "to_state": to_vals["state"],
                "to_country": to_vals["country"],
                "to_pincode": to_vals["pincode"],
            })

    @staticmethod
    def _prepare_company_address_vals(invoice):
        partner = invoice.company_id.partner_id
        return {
            "partner_id": partner.id if partner else False,
            "name": invoice.company_id.name or (partner.name if partner else False),
            "address": "\n".join(part for part in [partner.street, partner.street2] if part) if partner else False,
            "mobile": invoice.company_id.phone or (partner.phone if partner else False) or (partner.mobile if partner else False),
            "city": partner.city if partner else False,
            "state": partner.state_id.name if partner and partner.state_id else False,
            "country": partner.country_id.name if partner and partner.country_id else False,
            "pincode": partner.zip if partner else False,
        }

    @staticmethod
    def _prepare_invoice_address_vals(partner, name, mobile, address, city, state, country, pincode):
        return {
            "partner_id": partner.id if partner else False,
            "name": name or (partner.name if partner else False),
            "address": address or ("\n".join(part for part in [partner.street, partner.street2] if part) if partner else False),
            "mobile": mobile or (partner.mobile if partner else False) or (partner.phone if partner else False),
            "city": city or (partner.city if partner else False),
            "state": state or (partner.state_id.name if partner and partner.state_id else False),
            "country": country or (partner.country_id.name if partner and partner.country_id else False),
            "pincode": pincode or (partner.zip if partner else False),
        }

    @staticmethod
    def _format_partner_address(partner):
        if not partner:
            return False

        parts = [
            partner.street,
            partner.street2,
            partner.city,
            partner.state_id.name if partner.state_id else False,
            partner.zip,
            partner.country_id.name if partner.country_id else False,
        ]
        return "\n".join(part for part in parts if part) or False


class PackingOrderLine(models.Model):
    _name = "packing.order.line"
    _description = "Packing Order Line"
    _order = "id"

    packing_id = fields.Many2one("packing.order", string="Packing Order", required=True, ondelete="cascade")
    product_id = fields.Many2one("product.product", string="Product", required=True)
    description = fields.Char(string="Description")
    quantity = fields.Float(string="Quantity", digits="Product Unit of Measure")
    uom_id = fields.Many2one("uom.uom", string="UoM")
