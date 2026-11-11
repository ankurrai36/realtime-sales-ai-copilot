import re
import time
import logging
from typing import Optional, Dict, Any

from automation.scrapers import scrape_salesforce_lead

logger = logging.getLogger(__name__)


class SalesforceClient:
    """Controls Salesforce Lightning CTI softphone and DOM dispositions via Playwright CDP."""

    def __init__(self, interface=None, status_queue=None):
        self.interface = interface
        self.status_queue = status_queue
        self.page = None
        self.current_lead_data: Dict[str, Any] = {}
        self.is_call_active: bool = False

    def set_page(self, page):
        self.page = page

    def _locate_dialer_frame(self):
        """Scans page frame hierarchy for embedded CTI softphone iframe."""
        if not self.page:
            return None

        for frame in self.page.frames:
            name = str(frame.name or "").upper()
            url = str(frame.url or "").lower()
            if any(token in name or token in url for token in ("VERVE", "SFDCSOFTPHONE", "agentmini", "softphone")):
                return frame
        return None

    def get_softphone_status(self) -> str:
        """Polls CTI softphone iframe to determine active telephony state."""
        try:
            dialer_frame = self._locate_dialer_frame()
            if not dialer_frame:
                return "IDLE"

            # Check for live connected call indicator
            incall_elem = dialer_frame.locator(".incall, .connected, [data-status='incall'], .timer-active").filter(visible=True)
            if incall_elem.count() > 0:
                return "INCALL"

            ringing_elem = dialer_frame.locator(".ringing, [data-status='ringing']").filter(visible=True)
            if ringing_elem.count() > 0:
                return "RINGING"

            wrapup_elem = dialer_frame.locator(".wrapup, [data-status='wrapup']").filter(visible=True)
            if wrapup_elem.count() > 0:
                return "WRAPUP"

        except Exception as e:
            logger.debug("Softphone poll exception: %s", e)

        return "IDLE"

    def scrape_active_lead(self) -> Dict[str, str]:
        """Scrapes lead record from current active tab."""
        if not self.page:
            return {}
        data = scrape_salesforce_lead(self.page)
        if data and data.get("opp_id") != "N/A":
            self.current_lead_data = data
            if self.status_queue:
                self.status_queue.put(("LEAD_DATA_SCRAPED", data))
        return data

    def close_subtab(self):
        """Disposes of finished CRM sub-tab to maintain browser performance."""
        if not self.page:
            return
        try:
            pattern = re.compile(r"Close .+ \| (Opportunity|Lead|Task)", re.I)
            close_btn = self.page.get_by_role("button", name=pattern)
            if close_btn.count() > 0:
                close_btn.first.click(timeout=3000)
        except Exception as e:
            logger.debug("Sub-tab close error (ignored): %s", e)

    def apply_disposition(self, category: str = "NO_RESPONSE", notes: str = ""):
        """Selects disposition dropdown and commits CRM wrap-up notes."""
        if not self.page:
            return False

        try:
            dialer_frame = self._locate_dialer_frame() or self.page
            # Target PrimeNG and standard custom combobox options
            combobox = dialer_frame.locator("span.p-select-label, div[role='combobox'], select[name*='disp' i]").first
            if combobox.count() > 0:
                combobox.click(timeout=3000)
                time.sleep(0.3)

                # Select option matching category
                opt = dialer_frame.locator(f"li[role='option']:has-text('{category}'), option:has-text('{category}')").first
                if opt.count() > 0:
                    opt.click(timeout=3000)

            # Insert notes if text box exists
            if notes:
                notes_box = dialer_frame.locator("textarea[name*='comment' i], textarea#comments").first
                if notes_box.count() > 0:
                    notes_box.fill(notes)

            # Click save / submit
            save_btn = dialer_frame.locator("button:has-text('Save'), button:has-text('Submit')").first
            if save_btn.count() > 0:
                save_btn.click(timeout=3000)
                return True
        except Exception as e:
            logger.error("Failed to apply disposition '%s': %s", category, e)

        return False
