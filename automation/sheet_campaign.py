import os
import re
import csv
import logging
import threading
from typing import List, Dict, Any, Optional

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

logger = logging.getLogger(__name__)


class SheetCampaignManager:
    """Parses and manages tabular lead batches (.xlsx, .csv) with in-place feedback logging."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path
        self.leads: List[Dict[str, Any]] = []
        self.current_index: int = 0
        self.total_leads: int = 0
        self.file_type: Optional[str] = None
        self.lock = threading.Lock()

        self.col_map: Dict[str, Optional[int]] = {
            "name": None,
            "phone": None,
            "email": None,
            "stage": None,
            "program": None,
            "remarks": None
        }

        if file_path:
            self.load_sheet(file_path)

    def load_sheet(self, file_path: str) -> bool:
        """Loads and indexes lead batch from spreadsheet."""
        if not os.path.exists(file_path):
            logger.error("Campaign file not found: %s", file_path)
            return False

        self.file_path = file_path
        self.leads = []
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".csv":
            self.file_type = "csv"
            return self._load_csv()
        elif ext in (".xlsx", ".xlsm"):
            self.file_type = "xlsx"
            return self._load_xlsx()
        else:
            logger.error("Unsupported file extension '%s' for campaign batch.", ext)
            return False

    def _load_csv(self) -> bool:
        try:
            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                headers = next(reader, None)
                if not headers:
                    return False
                self._map_headers(headers)

                for row_idx, row in enumerate(reader, start=2):
                    lead = self._parse_row(row, row_idx)
                    if lead:
                        self.leads.append(lead)

            self.total_leads = len(self.leads)
            logger.info("Loaded %d leads from CSV file.", self.total_leads)
            return True
        except Exception as e:
            logger.error("Error reading CSV campaign: %s", e)
            return False

    def _load_xlsx(self) -> bool:
        if not OPENPYXL_AVAILABLE:
            logger.error("openpyxl is required to parse .xlsx files.")
            return False

        try:
            wb = openpyxl.load_workbook(self.file_path, data_only=True)
            sheet = wb.active
            headers = [cell.value for cell in sheet[1]]
            self._map_headers(headers)

            for row_idx, row_cells in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                lead = self._parse_row(list(row_cells), row_idx)
                if lead:
                    self.leads.append(lead)

            self.total_leads = len(self.leads)
            logger.info("Loaded %d leads from XLSX workbook.", self.total_leads)
            return True
        except Exception as e:
            logger.error("Error reading XLSX campaign: %s", e)
            return False

    def _map_headers(self, headers: List[Any]):
        """Fuzzy matches noisy spreadsheet header variations to canonical fields."""
        for idx, h in enumerate(headers):
            if not h:
                continue
            h_str = str(h).strip().lower()
            if any(k in h_str for k in ("name", "prospect", "student", "customer", "contact")):
                if self.col_map["name"] is None:
                    self.col_map["name"] = idx
            elif any(k in h_str for k in ("phone", "mobile", "contact no", "cell")):
                if self.col_map["phone"] is None:
                    self.col_map["phone"] = idx
            elif any(k in h_str for k in ("email", "mail")):
                if self.col_map["email"] is None:
                    self.col_map["email"] = idx
            elif any(k in h_str for k in ("stage", "status")):
                if self.col_map["stage"] is None:
                    self.col_map["stage"] = idx
            elif any(k in h_str for k in ("program", "course", "product")):
                if self.col_map["program"] is None:
                    self.col_map["program"] = idx
            elif any(k in h_str for k in ("remark", "comment", "note", "disposition")):
                if self.col_map["remarks"] is None:
                    self.col_map["remarks"] = idx

    def _parse_row(self, row: List[Any], row_idx: int) -> Optional[Dict[str, Any]]:
        def get_val(key: str) -> str:
            idx = self.col_map.get(key)
            if idx is not None and idx < len(row) and row[idx] is not None:
                return str(row[idx]).strip()
            return ""

        phone = get_val("phone")
        if not phone:
            return None

        return {
            "row_idx": row_idx,
            "lead_name": get_val("name") or "Prospective Lead",
            "primary_phone": phone,
            "email": get_val("email") or "N/A",
            "stage": get_val("stage") or "New",
            "program_name": get_val("program") or "Executive Program",
            "remarks": get_val("remarks")
        }

    def get_next_lead(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if self.current_index < len(self.leads):
                lead = self.leads[self.current_index]
                self.current_index += 1
                return lead
        return None

    def update_lead_remark(self, row_idx: int, remark_text: str):
        """Writes disposition remarks back into the physical spreadsheet."""
        with self.lock:
            if self.file_type == "xlsx" and OPENPYXL_AVAILABLE:
                try:
                    wb = openpyxl.load_workbook(self.file_path)
                    sheet = wb.active
                    rem_col = (self.col_map.get("remarks") or len(self.col_map)) + 1
                    sheet.cell(row=row_idx, column=rem_col, value=remark_text)
                    wb.save(self.file_path)
                except Exception as e:
                    logger.error("Failed saving remark to XLSX: %s", e)
