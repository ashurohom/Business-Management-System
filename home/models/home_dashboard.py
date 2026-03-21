from odoo import api, fields, models


class HomeDashboard(models.Model):
    _name = "home.dashboard"
    _description = "Home Dashboard"

    name = fields.Char(default="Home Dashboard", readonly=True)
    filter_date_from = fields.Date(string="Date From")
    filter_date_to = fields.Date(string="Date To")
    filter_partner_id = fields.Many2one("res.partner", string="Customer")
    filter_user_id = fields.Many2one("res.users", string="User")

    # User panel (current user only)
    user_total_sale = fields.Monetary(string="Total Sale (User)", compute="_compute_kpis", currency_field="currency_id")
    user_total_purchase = fields.Monetary(string="Total Purchase (User)", compute="_compute_kpis", currency_field="currency_id")
    user_sale_payment_due = fields.Monetary(string="Sale Payment Due (User)", compute="_compute_kpis", currency_field="currency_id")
    user_purchase_payment_due = fields.Monetary(string="Purchase Payment Due (User)", compute="_compute_kpis", currency_field="currency_id")
    user_stock_alert_ordered = fields.Integer(string="Products Stock Alert (User)", compute="_compute_kpis")
    user_pending_shipment = fields.Integer(string="Pending Shipment (User)", compute="_compute_kpis")
    user_pending_job_work = fields.Integer(string="Pending Job Work (User)", compute="_compute_kpis")

    # Admin panel (all data)
    admin_total_sale = fields.Monetary(string="Total Sale (All)", compute="_compute_kpis", currency_field="currency_id")
    admin_total_purchase = fields.Monetary(string="Total Purchase (All)", compute="_compute_kpis", currency_field="currency_id")
    admin_sale_payment_due = fields.Monetary(string="Sale Payment Due (All)", compute="_compute_kpis", currency_field="currency_id")
    admin_purchase_payment_due = fields.Monetary(string="Purchase Payment Due (All)", compute="_compute_kpis", currency_field="currency_id")
    admin_stock_alert_ordered = fields.Integer(string="Products Stock Alert (All)", compute="_compute_kpis")
    admin_pending_shipment = fields.Integer(string="Pending Shipment (All)", compute="_compute_kpis")
    admin_pending_job_work = fields.Integer(string="Pending Job Work (All)", compute="_compute_kpis")

    currency_id = fields.Many2one("res.currency", compute="_compute_currency", store=False)

    @api.depends_context("allowed_company_ids", "uid")
    def _compute_currency(self):
        for rec in self:
            rec.currency_id = self.env.company.currency_id

    def _company_domain(self):
        company_ids = self.env.companies.ids
        return [("company_id", "in", company_ids)]

    def _due_domain(self, move_type):
        return [
            ("move_type", "=", move_type),
            ("state", "=", "posted"),
            ("payment_state", "not in", ["paid", "reversed", "invoicing_legacy"]),
        ]

    def _sum_amount(self, model_name, domain, field_name="amount_total"):
        groups = self.env[model_name].read_group(domain, [field_name], [])
        return groups and groups[0].get(field_name) or 0.0

    def _count_records(self, model_name, domain):
        return self.env[model_name].search_count(domain)

    def _append_filters(self, domain, model, date_field=None, partner_field=None, user_fields=None):
        user_fields = user_fields or []
        if self.filter_date_from and date_field and date_field in model._fields:
            domain.append((date_field, ">=", self.filter_date_from))
        if self.filter_date_to and date_field and date_field in model._fields:
            domain.append((date_field, "<=", self.filter_date_to))
        if self.filter_partner_id and partner_field and partner_field in model._fields:
            domain.append((partner_field, "=", self.filter_partner_id.id))
        if self.filter_user_id and user_fields:
            valid_user_fields = [field_name for field_name in user_fields if field_name in model._fields]
            if valid_user_fields:
                user_domain = ["|"] * (len(valid_user_fields) - 1) + [
                    (field_name, "=", self.filter_user_id.id) for field_name in valid_user_fields
                ]
                domain += user_domain
        return domain

    def _pending_job_work_count(self, scope="all"):
        # Prefer custom Job Work model if available, otherwise fallback to Manufacturing Orders.
        if "job.work" in self.env:
            job_model = self.env["job.work"]
            job_domain = [("state", "not in", ["done", "cancel"])]
            self._append_filters(
                job_domain,
                job_model,
                date_field="date" if "date" in job_model._fields else "create_date",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )
            if scope == "user":
                if "user_id" in job_model._fields:
                    job_domain.append(("user_id", "=", self.env.user.id))
                elif "create_uid" in job_model._fields:
                    job_domain.append(("create_uid", "=", self.env.user.id))
            return self._count_records("job.work", job_domain)

        mo_model = self.env["mrp.production"]
        mo_domain = self._company_domain() + [("state", "not in", ["done", "cancel"])]
        self._append_filters(
            mo_domain,
            mo_model,
            date_field="date_start" if "date_start" in mo_model._fields else "create_date",
            partner_field="partner_id",
            user_fields=["user_id", "create_uid"],
        )
        if scope == "user":
            if "user_id" in mo_model._fields:
                mo_domain.append(("user_id", "=", self.env.user.id))
            else:
                mo_domain.append(("create_uid", "=", self.env.user.id))
        return self._count_records("mrp.production", mo_domain)

    @api.depends(
        "filter_date_from",
        "filter_date_to",
        "filter_partner_id",
        "filter_user_id",
    )
    @api.depends_context("allowed_company_ids", "uid")
    def _compute_kpis(self):
        user = self.env.user

        company_domain = self._company_domain()

        for rec in self:
            # Admin / All panel
            admin_sale_domain = company_domain + [("state", "in", ["sale", "done"])]
            rec._append_filters(
                admin_sale_domain,
                rec.env["sale.order"],
                date_field="date_order",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )
            admin_purchase_domain = company_domain + [("state", "in", ["purchase", "done"])]
            rec._append_filters(
                admin_purchase_domain,
                rec.env["purchase.order"],
                date_field="date_order",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )
            admin_sale_due_domain = company_domain + self._due_domain("out_invoice")
            rec._append_filters(
                admin_sale_due_domain,
                rec.env["account.move"],
                date_field="invoice_date",
                partner_field="partner_id",
                user_fields=["invoice_user_id", "create_uid"],
            )
            admin_purchase_due_domain = company_domain + self._due_domain("in_invoice")
            rec._append_filters(
                admin_purchase_due_domain,
                rec.env["account.move"],
                date_field="invoice_date",
                partner_field="partner_id",
                user_fields=["invoice_user_id", "create_uid"],
            )
            admin_low_stock_domain = [("type", "=", "product"), ("qty_available", "<", 5)]
            rec._append_filters(
                admin_low_stock_domain,
                rec.env["product.product"],
                date_field="create_date",
                partner_field=None,
                user_fields=["create_uid", "write_uid"],
            )
            admin_shipment_domain = company_domain + [
                ("picking_type_code", "=", "outgoing"),
                ("state", "not in", ["done", "cancel"]),
            ]
            rec._append_filters(
                admin_shipment_domain,
                rec.env["stock.picking"],
                date_field="scheduled_date",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )

            # User panel
            user_sale_domain = company_domain + [
                ("state", "in", ["sale", "done"]),
                ("user_id", "=", user.id),
            ]
            rec._append_filters(
                user_sale_domain,
                rec.env["sale.order"],
                date_field="date_order",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )
            user_purchase_domain = company_domain + [
                ("state", "in", ["purchase", "done"]),
                ("user_id", "=", user.id),
            ]
            rec._append_filters(
                user_purchase_domain,
                rec.env["purchase.order"],
                date_field="date_order",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )
            user_sale_due_domain = company_domain + self._due_domain("out_invoice") + [
                "|", ("invoice_user_id", "=", user.id), ("create_uid", "=", user.id),
            ]
            rec._append_filters(
                user_sale_due_domain,
                rec.env["account.move"],
                date_field="invoice_date",
                partner_field="partner_id",
                user_fields=["invoice_user_id", "create_uid"],
            )
            user_purchase_due_domain = company_domain + self._due_domain("in_invoice") + [
                "|", ("invoice_user_id", "=", user.id), ("create_uid", "=", user.id),
            ]
            rec._append_filters(
                user_purchase_due_domain,
                rec.env["account.move"],
                date_field="invoice_date",
                partner_field="partner_id",
                user_fields=["invoice_user_id", "create_uid"],
            )
            user_low_stock_domain = [("type", "=", "product"), ("qty_available", "<", 5)]
            rec._append_filters(
                user_low_stock_domain,
                rec.env["product.product"],
                date_field="create_date",
                partner_field=None,
                user_fields=["create_uid", "write_uid"],
            )
            user_shipment_domain = company_domain + [
                ("picking_type_code", "=", "outgoing"),
                ("state", "not in", ["done", "cancel"]),
                "|", ("user_id", "=", user.id), ("create_uid", "=", user.id),
            ]
            rec._append_filters(
                user_shipment_domain,
                rec.env["stock.picking"],
                date_field="scheduled_date",
                partner_field="partner_id",
                user_fields=["user_id", "create_uid"],
            )

            rec.admin_total_sale = self._sum_amount("sale.order", admin_sale_domain, "amount_total")
            rec.admin_total_purchase = self._sum_amount("purchase.order", admin_purchase_domain, "amount_total")
            rec.admin_sale_payment_due = self._sum_amount("account.move", admin_sale_due_domain, "amount_residual")
            rec.admin_purchase_payment_due = self._sum_amount("account.move", admin_purchase_due_domain, "amount_residual")
            rec.admin_stock_alert_ordered = self._count_records("product.product", admin_low_stock_domain)
            rec.admin_pending_shipment = self._count_records("stock.picking", admin_shipment_domain)
            rec.admin_pending_job_work = rec._pending_job_work_count("all")

            rec.user_total_sale = self._sum_amount("sale.order", user_sale_domain, "amount_total")
            rec.user_total_purchase = self._sum_amount("purchase.order", user_purchase_domain, "amount_total")
            rec.user_sale_payment_due = self._sum_amount("account.move", user_sale_due_domain, "amount_residual")
            rec.user_purchase_payment_due = self._sum_amount("account.move", user_purchase_due_domain, "amount_residual")
            rec.user_stock_alert_ordered = self._count_records("product.product", user_low_stock_domain)
            rec.user_pending_shipment = self._count_records("stock.picking", user_shipment_domain)
            rec.user_pending_job_work = rec._pending_job_work_count("user")

    def action_refresh_dashboard(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_apply_filters(self):
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_clear_filters(self):
        self.write(
            {
                "filter_date_from": False,
                "filter_date_to": False,
                "filter_partner_id": False,
                "filter_user_id": False,
            }
        )
        return {"type": "ir.actions.client", "tag": "reload"}
