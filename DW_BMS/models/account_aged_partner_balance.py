from odoo import api, fields, models


class AccountAgedTrialBalance(models.TransientModel):
    _inherit = "account.aged.trial.balance"

    partner_ids = fields.Many2many(
        "res.partner",
        string="Partners",
    )

    def pre_print_report(self, data):
        data = super().pre_print_report(data)
        data["form"].update(
            self.read(["partner_ids"])[0]
        )
        return data


class ReportAgedPartnerBalance(models.AbstractModel):
    _inherit = "report.base_accounting_kit.report_agedpartnerbalance"

    @api.model
    def _get_report_values(self, docids, data=None):
        res = super()._get_report_values(docids, data)

        partner_ids = data.get("form", {}).get("partner_ids", [])
        if partner_ids:
            filtered_lines = []
            new_total = [0.0] * 7

            for line in res.get("get_partner_lines", []):
                if line.get("partner_id") in partner_ids:
                    filtered_lines.append(line)

                    new_total[6] += line.get("direction", 0.0)
                    for i in range(5):
                        new_total[i] += line.get(str(i), 0.0)
                    new_total[5] += line.get("total", 0.0)

            res["get_partner_lines"] = filtered_lines
            res["get_direction"] = new_total

        return res
