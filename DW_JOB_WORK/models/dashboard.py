from odoo import fields, models, tools


class JobWorkDashboard(models.Model):
    _name = "dw.job.work.dashboard"
    _description = "Job Work Dashboard"
    _auto = False
    _rec_name = "contractor_id"

    contractor_id = fields.Many2one("res.partner", string="Contractor", readonly=True)
    total_remaining = fields.Float(string="Total Remaining Raw Material", readonly=True)

    def init(self):
        self.env.cr.execute(
            """
            SELECT c.relkind
            FROM pg_class c
            WHERE c.relname = %s
            """,
            (self._table,),
        )
        result = self.env.cr.fetchone()
        if result and result[0] == "r":
            self.env.cr.execute(f"DROP TABLE {self._table} CASCADE")
        else:
            tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(
            """
            CREATE OR REPLACE VIEW dw_job_work_dashboard AS (
                SELECT
                    MIN(line.id) AS id,
                    issue.contractor_id AS contractor_id,
                    COALESCE(SUM(line.remaining_qty), 0) AS total_remaining
                FROM dw_job_work_issue_line line
                JOIN dw_job_work_issue issue ON issue.id = line.issue_id
                WHERE issue.state = 'confirmed'
                GROUP BY issue.contractor_id
                HAVING COALESCE(SUM(line.remaining_qty), 0) > 0
            )
            """
        )
