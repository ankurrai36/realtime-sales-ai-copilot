import re
import time
import logging
from typing import Dict, Any, Optional

try:
    from playwright.sync_api import Page, Frame, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger(__name__)


def _fast_probe_field(frame: Any, label_name: str, is_multiline: bool = False) -> str:
    """High-speed LWC container query for named Salesforce fields."""
    try:
        selector = (
            f"records-record-layout-item:has-text('{label_name}'), "
            f"records-highlights-details-item:has-text('{label_name}'), "
            f"div.slds-form-element:has-text('{label_name}')"
        )
        loc = frame.locator(selector).filter(visible=True).first
        if loc.count() > 0:
            raw_text = loc.inner_text()
            clean_val = raw_text.replace(label_name, "").strip()

            # Strip Salesforce action labels and preview tags
            noise_tokens = ["Edit", "Help", "Click to edit", "Show more", "Open Preview"]
            for token in noise_tokens:
                clean_val = re.sub(rf"\b{token}\b", "", clean_val, flags=re.IGNORECASE).strip()
            clean_val = re.sub(r"Open .* Preview", "", clean_val, flags=re.IGNORECASE).strip()

            if clean_val and clean_val != "N/A":
                return clean_val if is_multiline else clean_val.split("\n")[0].strip()
    except Exception:
        pass
    return "N/A"


def scrape_salesforce_lead(page: Any) -> Dict[str, str]:
    """Scrapes structured lead record from active Salesforce Lightning workspace."""
    if not page:
        return {}

    target_frame = page.main_frame
    for f in page.frames:
        if "lightning.force.com" in f.url and "one/one.app" in f.url:
            target_frame = f
            break

    try:
        target_frame.wait_for_selector("records-record-layout-section", timeout=6000)
        time.sleep(0.3)
    except Exception:
        return {}

    info = {
        "opp_id": _fast_probe_field(target_frame, "Opportunity ID"),
        "program_name": _fast_probe_field(target_frame, "Program"),
        "email": _fast_probe_field(target_frame, "Email Id"),
        "primary_phone": _fast_probe_field(target_frame, "Mobile Number"),
        "lead_name": _fast_probe_field(target_frame, "Account Name"),
        "stage": _fast_probe_field(target_frame, "Stage"),
        "alternate_mobile_number": _fast_probe_field(target_frame, "Alternate Mobile Number"),
        "latest_notes": _fast_probe_field(target_frame, "Latest Activity Comments", is_multiline=True)
    }

    for k, v in info.items():
        if not v:
            info[k] = "N/A"

    return info


def scrape_dialer_lead(page: Any) -> Dict[str, str]:
    """Scrapes prospect data from active web dialer form fields."""
    results = {
        "opp_id": "N/A",
        "email": "N/A",
        "primary_phone": "N/A",
        "program_name": "N/A",
        "lead_name": "N/A",
        "stage": "Outbound Dialer"
    }

    if not page:
        return results

    surfaces = [page] + [f for f in page.frames if f != page.main_frame]

    for surface in surfaces:
        try:
            # 1. Opportunity ID
            opp_loc = surface.locator("input[name*='opportunityid' i], input#opportunityid").filter(visible=True).first
            if opp_loc.count() > 0:
                val = (opp_loc.input_value() or "").strip()
                if val:
                    results["opp_id"] = val

            # 2. Prospect Name
            name_loc = surface.locator("input[name*='opportunityname' i], input#opportunityname").filter(visible=True).first
            if name_loc.count() > 0:
                val = (name_loc.input_value() or "").strip()
                if val and not any(c.isdigit() for c in val):
                    results["lead_name"] = val.title()

            # 3. Phone Number
            phone_loc = surface.locator("input[name*='phone' i], select[name*='phone' i]").filter(visible=True).first
            if phone_loc.count() > 0:
                clean_digits = "".join(filter(str.isdigit, phone_loc.input_value() or ""))
                if 10 <= len(clean_digits) <= 13:
                    results["primary_phone"] = clean_digits

            # 4. Email Address
            email_loc = surface.locator("input[name*='email' i], input#emailid").filter(visible=True).first
            if email_loc.count() > 0:
                val = (email_loc.input_value() or "").strip()
                if "@" in val and "." in val:
                    results["email"] = val
        except Exception:
            continue

    return results
