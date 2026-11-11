import os
import json
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from config.settings import settings

logger = logging.getLogger(__name__)
_db_lock = threading.Lock()


def load_database() -> Dict[str, Any]:
    """Reads the JSON leads database into memory with auto-recovery and fallback."""
    with _db_lock:
        db_path = settings.database_file
        if not db_path.exists():
            # If active database does not exist, initialize from mock_leads if available
            if settings.mock_leads_file.exists():
                try:
                    with open(settings.mock_leads_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    save_database(data)
                    return data
                except Exception as e:
                    logger.warning("Could not initialize database from mock leads: %s", e)
            return {}

        try:
            with open(db_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            logger.error("Failed to load leads database: %s", e)
            return {}


def save_database(data: Dict[str, Any]):
    """Commits in-memory database to persistent storage with atomic hardware flush."""
    with _db_lock:
        try:
            db_path = settings.database_file
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
        except IOError as e:
            logger.critical("Critical I/O error flushing database to disk: %s", e)


def _ensure_lead_schema(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Guarantees presence of required metrics and relational collection arrays."""
    lead.setdefault("whatsapp_reachouts", 0)
    lead.setdefault("email_reachouts", 0)
    lead.setdefault("sms_reachouts", 0)
    lead.setdefault("summaries", [])
    lead.setdefault("call_history", [])
    lead.setdefault("message_history", [])
    lead.setdefault("total_reachouts", 0)
    lead.setdefault("consecutive_no_responses", 0)
    return lead


def create_or_get_lead(opp_id: str, scraped_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Retrieves an existing lead or instantiates a new record with sanitized fields."""
    if not opp_id:
        return {}

    sanitized_id = str(opp_id).strip().upper()
    db = load_database()
    lead = db.get(sanitized_id)

    if lead:
        for key, val in (scraped_data or {}).items():
            if key not in ("summaries", "call_history", "message_history", "total_reachouts", "consecutive_no_responses"):
                if val and val != "N/A":
                    lead[key] = val
        lead = _ensure_lead_schema(lead)
    else:
        meta = scraped_data or {}
        lead = {
            "opp_id": sanitized_id,
            "lead_name": meta.get("lead_name", "Prospective Candidate"),
            "program_name": meta.get("program_name", "N/A"),
            "primary_phone": meta.get("primary_phone", "N/A"),
            "email": meta.get("email", "N/A"),
            "stage": meta.get("stage", "Enquiry"),
            "summaries": [],
            "call_history": [],
            "message_history": [],
            "total_reachouts": 0,
            "consecutive_no_responses": 0,
            "whatsapp_reachouts": 0,
            "email_reachouts": 0,
            "sms_reachouts": 0
        }

    db[sanitized_id] = lead
    save_database(db)
    return lead


def update_lead_history(opp_id: str, transcript: str):
    """Appends session transcript snapshot to lead record."""
    if not opp_id or not transcript or opp_id == "N/A":
        return

    sanitized_id = str(opp_id).strip().upper()
    db = load_database()
    if sanitized_id in db:
        db[sanitized_id].setdefault("call_history", []).append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "transcript": transcript
        })
        save_database(db)


def get_lead_history(opp_id: str) -> List[Dict[str, str]]:
    """Fetches chronological call transcript history for an Opportunity ID."""
    if not opp_id or opp_id == "N/A":
        return []
    db = load_database()
    lead = db.get(str(opp_id).strip().upper(), {})
    return lead.get("call_history", [])


def update_lead_summaries(opp_id: str, summary: str):
    """Stores structured post-call summary note in lead history."""
    if not opp_id or not summary or opp_id == "N/A":
        return

    sanitized_id = str(opp_id).strip().upper()
    db = load_database()
    if sanitized_id in db:
        db[sanitized_id].setdefault("summaries", []).append(summary)
        save_database(db)


def get_lead_summaries(opp_id: str) -> List[str]:
    """Retrieves list of past CRM disposition summaries."""
    if not opp_id or opp_id == "N/A":
        return []
    db = load_database()
    lead = db.get(str(opp_id).strip().upper(), {})
    return lead.get("summaries", [])
