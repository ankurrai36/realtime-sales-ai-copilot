import time
import logging
from typing import Dict, Any, Optional

from automation.scrapers import scrape_dialer_lead

logger = logging.getLogger(__name__)


class ContaqueClient:
    """Controls the Contaque AICX cloud dialer interface via Playwright CDP (Port 9223)."""

    def __init__(self, interface=None, status_queue=None):
        self.interface = interface
        self.status_queue = status_queue
        self.page = None
        self.current_lead_data: Dict[str, Any] = {}

    def set_page(self, page):
        self.page = page

    def clear_state(self):
        self.current_lead_data = {}

    def scrape_active_lead(self) -> Dict[str, str]:
        """Scrapes prospect data from active Contaque form."""
        if not self.page:
            return {}
        data = scrape_dialer_lead(self.page)
        if data and data.get("opp_id") != "N/A":
            self.current_lead_data = data
            if self.status_queue:
                self.status_queue.put(("LEAD_DATA_SCRAPED", data))
        return data

    def trigger_dial(self, phone_number: str) -> bool:
        """Enters phone number into dialer keypad and triggers call."""
        if not self.page or not phone_number:
            return False

        try:
            dial_input = self.page.locator("input[placeholder*='phone' i], input#manual_dial").first
            if dial_input.count() > 0:
                dial_input.fill(phone_number)
                dial_btn = self.page.locator("button:has-text('Dial'), button.dial-btn").first
                if dial_btn.count() > 0:
                    dial_btn.click()
                    return True
        except Exception as e:
            logger.error("Failed triggering dial for %s: %s", phone_number, e)

        return False
