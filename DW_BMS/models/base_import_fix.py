import logging

from odoo import models

_logger = logging.getLogger(__name__)


class BaseImport(models.TransientModel):
    _inherit = "base_import.import"

    def _is_effectively_empty_value(self, value):
        if value in (None, False):
            return True
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return True
            if stripped.lower() in {"none", "null", "nan"}:
                return True
        return False

    def _normalize_cell_value(self, value):
        if self._is_effectively_empty_value(value):
            return ""
        return value

    def _sanitize_import_none_values(self, data):
        sanitized_data = []
        skipped_empty_rows = 0

        for line in data:
            normalized_line = [self._normalize_cell_value(value) for value in line]
            if all(self._is_effectively_empty_value(value) for value in normalized_line):
                skipped_empty_rows += 1
                continue
            sanitized_data.append(normalized_line)

        if skipped_empty_rows:
            _logger.info(
                "Skipped %s fully empty row(s) during base import sanitization.",
                skipped_empty_rows,
            )
        return sanitized_data

    def _parse_import_data(self, data, import_fields, options):
        # Ensure parser/model.load never receives Python None-like tokens from XLS/XLSX.
        data = self._sanitize_import_none_values(data)
        return super()._parse_import_data(data, import_fields, options)

    def _parse_float_from_data(self, data, index, name, options):
        """
        Odoo's importer expects string values for float columns and calls .strip().
        Some XLSX cells can arrive as None/"None", which triggers validation errors.
        Normalize them to empty strings before the standard parser runs.
        """
        for line in data:
            if index >= len(line):
                continue
            value = line[index]
            if value in (None, False):
                line[index] = ""
                continue
            if isinstance(value, str):
                if value.strip().lower() in {"none", "null", "nan"}:
                    line[index] = ""
            else:
                line[index] = str(value)
        return super()._parse_float_from_data(data, index, name, options)
