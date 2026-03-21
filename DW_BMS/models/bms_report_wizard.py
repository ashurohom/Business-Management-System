import base64
from collections import defaultdict
from io import BytesIO

import xlsxwriter
from odoo import fields, models


class BmsReportWizard(models.TransientModel):
    _name = "bms.report.wizard"
    _description = "BMS Report Wizard"

    report_type = fields.Selection(
        [
            ("profit_loss", "Profit / Loss Report"),
            ("purchase_sales", "Purchase / Sales Report"),
            ("supplier_customer", "Supplier and Customer Report"),
            ("stock", "Stock Report"),
            ("product_purchase", "Products Purchase Report"),
            ("product_sale_user", "Products Sale Report with Usernames"),
            ("purchase_payment", "Purchase Payment / Pending Report"),
            ("sales_payment", "Sales Payment Report"),
            ("bank", "Bank Report"),
        ],
        required=True,
        default="profit_loss",
    )

    partner_id = fields.Many2one("res.partner", string="Customer / Supplier")
    partner_role = fields.Selection(
        [("all", "All"), ("customer", "Customer"), ("supplier", "Supplier")],
        default="all",
        string="Partner Type",
    )
    user_id = fields.Many2one("res.users", string="User")
    date_from = fields.Date(string="Date From")
    date_to = fields.Date(string="Date To")
    payment_status = fields.Selection(
        [
            ("all", "All"),
            ("paid", "Paid"),
            ("partial", "Partially Paid"),
            ("not_paid", "Not Paid"),
        ],
        default="all",
    )
    shipping_status = fields.Selection(
        [("all", "All"), ("done", "Delivered"), ("pending", "Pending")],
        default="all",
    )

    xlsx_file = fields.Binary(readonly=True)
    xlsx_filename = fields.Char(readonly=True)

    def _selection_label(self, field_name, value):
        return dict(self._fields[field_name].selection).get(value)

    def _date_domain(self, field_name):
        domain = []
        if self.date_from:
            domain.append((field_name, ">=", self.date_from))
        if self.date_to:
            domain.append((field_name, "<=", self.date_to))
        return domain

    def _payment_status_domain(self):
        if self.payment_status == "all":
            return []
        if self.payment_status == "paid":
            return [("payment_state", "=", "paid")]
        if self.payment_status == "partial":
            return [("payment_state", "=", "partial")]
        return [("payment_state", "in", ("not_paid", "in_payment"))]

    def _append_partner_role_domain(self, domain, relation_field="partner_id"):
        if self.partner_role == "customer":
            domain.append((f"{relation_field}.customer_rank", ">", 0))
        elif self.partner_role == "supplier":
            domain.append((f"{relation_field}.supplier_rank", ">", 0))
        return domain

    def _shipping_domain(self):
        if self.shipping_status == "all":
            return []
        if "picking_ids" not in self.env["sale.order"]._fields:
            return []
        if self.shipping_status == "done":
            return [("picking_ids.state", "=", "done")]
        return [("picking_ids.state", "not in", ("done", "cancel"))]

    def _base_filters(self):
        return {
            "partner": self.partner_id.display_name or "All",
            "partner_role": self._selection_label("partner_role", self.partner_role),
            "payment_status": self._selection_label("payment_status", self.payment_status),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "user": self.user_id.display_name or "All",
            "shipping_status": self._selection_label("shipping_status", self.shipping_status),
        }

    def _collect_profit_loss(self):
        invoice_domain = [("state", "=", "posted"), ("move_type", "in", ("out_invoice", "out_refund"))]
        bill_domain = [("state", "=", "posted"), ("move_type", "in", ("in_invoice", "in_refund"))]
        invoice_domain += self._date_domain("invoice_date")
        bill_domain += self._date_domain("invoice_date")
        if self.partner_id:
            invoice_domain.append(("partner_id", "=", self.partner_id.id))
            bill_domain.append(("partner_id", "=", self.partner_id.id))
        self._append_partner_role_domain(invoice_domain)
        self._append_partner_role_domain(bill_domain)
        invoice_domain += self._payment_status_domain()
        bill_domain += self._payment_status_domain()

        invoices = self.env["account.move"].search(invoice_domain)
        bills = self.env["account.move"].search(bill_domain)

        sales_amount = sum(
            move.amount_untaxed if move.move_type == "out_invoice" else -move.amount_untaxed for move in invoices
        )
        purchase_amount = sum(
            move.amount_untaxed if move.move_type == "in_invoice" else -move.amount_untaxed for move in bills
        )
        return {
            "sales_amount": sales_amount,
            "purchase_amount": purchase_amount,
            "profit_loss": sales_amount - purchase_amount,
        }

    def _collect_purchase_sales(self):
        sale_domain = [("state", "in", ("sale", "done"))] + self._date_domain("date_order")
        purchase_domain = [("state", "in", ("purchase", "done"))] + self._date_domain("date_order")
        if self.partner_id:
            sale_domain.append(("partner_id", "=", self.partner_id.id))
            purchase_domain.append(("partner_id", "=", self.partner_id.id))
        if self.user_id:
            sale_domain.append(("user_id", "=", self.user_id.id))
        self._append_partner_role_domain(sale_domain)
        self._append_partner_role_domain(purchase_domain)
        sale_domain += self._shipping_domain()

        sale_orders = self.env["sale.order"].search(sale_domain)
        purchase_orders = self.env["purchase.order"].search(purchase_domain)
        purchase_lines = []
        for order in purchase_orders:
            purchase_lines.append(
                {
                    "name": order.name,
                    "date": order.date_order.date() if order.date_order else False,
                    "partner": order.partner_id.display_name,
                    "amount": order.amount_total,
                }
            )
        sale_lines = []
        for order in sale_orders:
            sale_lines.append(
                {
                    "name": order.name,
                    "date": order.date_order.date() if order.date_order else False,
                    "partner": order.partner_id.display_name,
                    "user": order.user_id.display_name or "",
                    "amount": order.amount_total,
                }
            )
        return {
            "sale_total": sum(sale_orders.mapped("amount_total")),
            "purchase_total": sum(purchase_orders.mapped("amount_total")),
            "sale_lines": sale_lines,
            "purchase_lines": purchase_lines,
        }

    def _collect_supplier_customer(self):
        partner_domain = [("is_company", "=", True)]
        if self.partner_id:
            partner_domain.append(("id", "=", self.partner_id.id))
        customers = self.env["res.partner"].search(partner_domain + [("customer_rank", ">", 0)])
        suppliers = self.env["res.partner"].search(partner_domain + [("supplier_rank", ">", 0)])
        if self.partner_role == "customer":
            suppliers = self.env["res.partner"]
        elif self.partner_role == "supplier":
            customers = self.env["res.partner"]
        return {
            "customer_lines": [
                {
                    "name": partner.display_name,
                    "phone": partner.phone or "",
                    "email": partner.email or "",
                    "receivable": partner.credit,
                }
                for partner in customers
            ],
            "supplier_lines": [
                {
                    "name": partner.display_name,
                    "phone": partner.phone or "",
                    "email": partner.email or "",
                    "payable": partner.debit,
                }
                for partner in suppliers
            ],
        }

    def _collect_stock(self):
        products = self.env["product.product"].search([("type", "=", "product")])
        stock_lines = []
        for product in products:
            if not product.qty_available and not product.virtual_available:
                continue
            stock_lines.append(
                {
                    "product": product.display_name,
                    "qty_available": product.qty_available,
                    "forecast_qty": product.virtual_available,
                    "unit_cost": product.standard_price,
                    "stock_value": product.qty_available * product.standard_price,
                }
            )
        return {
            "stock_lines": stock_lines,
            "stock_total_qty": sum(line["qty_available"] for line in stock_lines),
            "stock_total_value": sum(line["stock_value"] for line in stock_lines),
        }

    def _collect_product_purchase(self):
        line_domain = [("order_id.state", "in", ("purchase", "done"))] + self._date_domain("order_id.date_order")
        if self.partner_id:
            line_domain.append(("order_id.partner_id", "=", self.partner_id.id))
        if self.user_id:
            line_domain.append(("order_id.user_id", "=", self.user_id.id))
        self._append_partner_role_domain(line_domain, "order_id.partner_id")
        lines = self.env["purchase.order.line"].search(line_domain)
        grouped = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
        for line in lines:
            key = line.product_id.display_name
            grouped[key]["qty"] += line.product_qty
            grouped[key]["amount"] += line.price_total
        return {
            "product_lines": [
                {"product": product, "qty": values["qty"], "amount": values["amount"]}
                for product, values in grouped.items()
            ]
        }

    def _collect_product_sale_user(self):
        line_domain = [("order_id.state", "in", ("sale", "done"))] + self._date_domain("order_id.date_order")
        if self.partner_id:
            line_domain.append(("order_id.partner_id", "=", self.partner_id.id))
        if self.user_id:
            line_domain.append(("order_id.user_id", "=", self.user_id.id))
        self._append_partner_role_domain(line_domain, "order_id.partner_id")
        line_domain += self._shipping_domain()
        lines = self.env["sale.order.line"].search(line_domain)
        grouped = defaultdict(lambda: {"qty": 0.0, "amount": 0.0})
        for line in lines:
            key = (line.product_id.display_name, line.order_id.user_id.display_name or "Undefined")
            grouped[key]["qty"] += line.product_uom_qty
            grouped[key]["amount"] += line.price_total
        return {
            "product_user_lines": [
                {
                    "product": product,
                    "user": user,
                    "qty": values["qty"],
                    "amount": values["amount"],
                }
                for (product, user), values in grouped.items()
            ]
        }

    def _collect_purchase_payment(self):
        domain = [("state", "=", "posted"), ("move_type", "in", ("in_invoice", "in_refund"))]
        domain += self._date_domain("invoice_date")
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        self._append_partner_role_domain(domain)
        domain += self._payment_status_domain()
        moves = self.env["account.move"].search(domain)
        lines = []
        total_paid = 0.0
        total_pending = 0.0
        for move in moves:
            paid_amount = move.amount_total - move.amount_residual
            total_paid += paid_amount
            total_pending += move.amount_residual
            lines.append(
                {
                    "name": move.name,
                    "date": move.invoice_date,
                    "partner": move.partner_id.display_name,
                    "total": move.amount_total,
                    "paid": paid_amount,
                    "pending": move.amount_residual,
                    "payment_state": move.payment_state,
                }
            )
        return {"payment_lines": lines, "total_paid": total_paid, "total_pending": total_pending}

    def _collect_sales_payment(self):
        domain = [("state", "=", "posted"), ("move_type", "in", ("out_invoice", "out_refund"))]
        domain += self._date_domain("invoice_date")
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        self._append_partner_role_domain(domain)
        domain += self._payment_status_domain()
        moves = self.env["account.move"].search(domain)
        lines = []
        total_paid = 0.0
        total_pending = 0.0
        for move in moves:
            paid_amount = move.amount_total - move.amount_residual
            total_paid += paid_amount
            total_pending += move.amount_residual
            lines.append(
                {
                    "name": move.name,
                    "date": move.invoice_date,
                    "partner": move.partner_id.display_name,
                    "total": move.amount_total,
                    "paid": paid_amount,
                    "pending": move.amount_residual,
                    "payment_state": move.payment_state,
                }
            )
        return {"payment_lines": lines, "total_paid": total_paid, "total_pending": total_pending}

    def _collect_bank(self):
        domain = [("state", "=", "posted")] + self._date_domain("date")
        if self.partner_id:
            domain.append(("partner_id", "=", self.partner_id.id))
        if self.user_id:
            domain.append(("create_uid", "=", self.user_id.id))
        payments = self.env["account.payment"].search(domain)
        bank_summary = defaultdict(float)
        bank_detail = []
        for payment in payments:
            bank_name = payment.journal_id.display_name or "Undefined"
            bank_summary[bank_name] += payment.amount
            bank_detail.append(
                {
                    "date": payment.date,
                    "name": payment.name,
                    "bank": bank_name,
                    "partner": payment.partner_id.display_name,
                    "amount": payment.amount,
                }
            )
        return {
            "bank_lines": [{"bank": bank, "amount": amount} for bank, amount in bank_summary.items()],
            "bank_detail_lines": bank_detail,
        }

    def _collect_data(self):
        self.ensure_one()
        payload = {}
        title = self._selection_label("report_type", self.report_type)
        if self.report_type == "profit_loss":
            payload = self._collect_profit_loss()
        elif self.report_type == "purchase_sales":
            payload = self._collect_purchase_sales()
        elif self.report_type == "supplier_customer":
            payload = self._collect_supplier_customer()
        elif self.report_type == "stock":
            payload = self._collect_stock()
        elif self.report_type == "product_purchase":
            payload = self._collect_product_purchase()
        elif self.report_type == "product_sale_user":
            payload = self._collect_product_sale_user()
        elif self.report_type == "purchase_payment":
            payload = self._collect_purchase_payment()
        elif self.report_type == "sales_payment":
            payload = self._collect_sales_payment()
        elif self.report_type == "bank":
            payload = self._collect_bank()

        return {
            "generated_on": fields.Datetime.now(),
            "report_type": self.report_type,
            "title": title,
            "filters": self._base_filters(),
            **payload,
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref("DW_BMS.action_bms_summary_pdf").report_action(self)

    def _write_table(self, sheet, row, headers, lines, bold, money):
        for col, header in enumerate(headers):
            sheet.write(row, col, header, bold)
        row += 1
        for line in lines:
            for col, value in enumerate(line):
                if isinstance(value, (int, float)):
                    sheet.write(row, col, value, money)
                else:
                    sheet.write(row, col, value if value is not False else "")
            row += 1
        return row + 1

    def action_generate_xlsx(self):
        self.ensure_one()
        data = self._collect_data()

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet("BMS Report")
        bold = workbook.add_format({"bold": True})
        money = workbook.add_format({"num_format": "#,##0.00"})

        row = 0
        sheet.write(row, 0, data["title"], bold)
        row += 2

        sheet.write(row, 0, "Filters", bold)
        row += 1
        for key, value in data["filters"].items():
            sheet.write(row, 0, key.replace("_", " ").title())
            sheet.write(row, 1, str(value or "-"))
            row += 1
        row += 2

        if data["report_type"] == "profit_loss":
            sheet.write(row, 0, "Sales Amount", bold)
            sheet.write(row, 1, data["sales_amount"], money)
            row += 1
            sheet.write(row, 0, "Purchase Amount", bold)
            sheet.write(row, 1, data["purchase_amount"], money)
            row += 1
            sheet.write(row, 0, "Profit / Loss", bold)
            sheet.write(row, 1, data["profit_loss"], money)
        elif data["report_type"] == "purchase_sales":
            sheet.write(row, 0, "Sales Total", bold)
            sheet.write(row, 1, data["sale_total"], money)
            row += 1
            sheet.write(row, 0, "Purchase Total", bold)
            sheet.write(row, 1, data["purchase_total"], money)
            row += 2
            row = self._write_table(
                sheet,
                row,
                ["Sale Order", "Date", "Customer", "User", "Amount"],
                [[l["name"], l["date"], l["partner"], l["user"], l["amount"]] for l in data["sale_lines"]],
                bold,
                money,
            )
            row = self._write_table(
                sheet,
                row,
                ["Purchase Order", "Date", "Supplier", "Amount"],
                [[l["name"], l["date"], l["partner"], l["amount"]] for l in data["purchase_lines"]],
                bold,
                money,
            )
        elif data["report_type"] == "supplier_customer":
            row = self._write_table(
                sheet,
                row,
                ["Customer", "Phone", "Email", "Receivable"],
                [[l["name"], l["phone"], l["email"], l["receivable"]] for l in data["customer_lines"]],
                bold,
                money,
            )
            row = self._write_table(
                sheet,
                row,
                ["Supplier", "Phone", "Email", "Payable"],
                [[l["name"], l["phone"], l["email"], l["payable"]] for l in data["supplier_lines"]],
                bold,
                money,
            )
        elif data["report_type"] == "stock":
            sheet.write(row, 0, "Total Qty", bold)
            sheet.write(row, 1, data["stock_total_qty"])
            row += 1
            sheet.write(row, 0, "Total Value", bold)
            sheet.write(row, 1, data["stock_total_value"], money)
            row += 2
            row = self._write_table(
                sheet,
                row,
                ["Product", "Qty Available", "Forecast Qty", "Unit Cost", "Stock Value"],
                [
                    [l["product"], l["qty_available"], l["forecast_qty"], l["unit_cost"], l["stock_value"]]
                    for l in data["stock_lines"]
                ],
                bold,
                money,
            )
        elif data["report_type"] == "product_purchase":
            row = self._write_table(
                sheet,
                row,
                ["Product", "Qty Purchased", "Amount"],
                [[l["product"], l["qty"], l["amount"]] for l in data["product_lines"]],
                bold,
                money,
            )
        elif data["report_type"] == "product_sale_user":
            row = self._write_table(
                sheet,
                row,
                ["Product", "User", "Qty Sold", "Amount"],
                [[l["product"], l["user"], l["qty"], l["amount"]] for l in data["product_user_lines"]],
                bold,
                money,
            )
        elif data["report_type"] in ("purchase_payment", "sales_payment"):
            sheet.write(row, 0, "Total Paid", bold)
            sheet.write(row, 1, data["total_paid"], money)
            row += 1
            sheet.write(row, 0, "Total Pending", bold)
            sheet.write(row, 1, data["total_pending"], money)
            row += 2
            row = self._write_table(
                sheet,
                row,
                ["Reference", "Date", "Partner", "Total", "Paid", "Pending", "Payment State"],
                [
                    [l["name"], l["date"], l["partner"], l["total"], l["paid"], l["pending"], l["payment_state"]]
                    for l in data["payment_lines"]
                ],
                bold,
                money,
            )
        elif data["report_type"] == "bank":
            row = self._write_table(
                sheet,
                row,
                ["Bank", "Amount"],
                [[l["bank"], l["amount"]] for l in data["bank_lines"]],
                bold,
                money,
            )
            row = self._write_table(
                sheet,
                row,
                ["Date", "Payment", "Bank", "Partner", "Amount"],
                [
                    [l["date"], l["name"], l["bank"], l["partner"], l["amount"]]
                    for l in data["bank_detail_lines"]
                ],
                bold,
                money,
            )

        workbook.close()
        file_data = base64.b64encode(output.getvalue())
        filename = f"bms_report_{fields.Date.today()}.xlsx"
        self.write({"xlsx_file": file_data, "xlsx_filename": filename})

        return {
            "type": "ir.actions.act_window",
            "res_model": "bms.report.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
