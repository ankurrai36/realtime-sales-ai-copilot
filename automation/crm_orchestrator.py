import time
import queue
import logging
import threading
from typing import Optional, Dict, Any

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from config.settings import settings
from automation.salesforce_client import SalesforceClient
from automation.contaque_client import ContaqueClient
from automation.outreach import OutreachDispatcher
from automation.sheet_campaign import SheetCampaignManager

logger = logging.getLogger(__name__)


class CRMOrchestrator:
    """Master CDP orchestrator connecting to Port 9222 (CRM), Port 9223 (Dialer/Mail), and Port 9224 (AI).

    Coordinates automated scraping, phone state monitoring, auto-disposition timers,
    and cross-channel messaging while guarding against race conditions.
    """

    def __init__(self, gui_app=None, status_queue=None, playwright_queue=None):
        self.gui_app = gui_app
        self.status_queue = status_queue
        self.playwright_queue = playwright_queue or queue.Queue()

        self.salesforce = SalesforceClient(interface=None, status_queue=status_queue)
        self.contaque = ContaqueClient(interface=None, status_queue=status_queue)
        self.outreach = OutreachDispatcher()
        self.sheet_manager: Optional[SheetCampaignManager] = None

        self.is_connected = False
        self.is_running = False
        self.call_in_progress = False

        self._playwright_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start_orchestrator(self):
        """Spawns background Playwright event thread."""
        if self._playwright_thread and self._playwright_thread.is_alive():
            return

        self._stop_event.clear()
        self._playwright_thread = threading.Thread(
            target=self._playwright_worker_loop,
            name="PlaywrightCDPWorker",
            daemon=True
        )
        self._playwright_thread.start()

    def stop_and_disconnect(self):
        """Global kill switch: disconnects browser handles and halts automation loops."""
        logger.info("Kill switch engaged. Halting CRM orchestrator...")
        self._stop_event.set()
        self.is_running = False
        self.is_connected = False
        self.call_in_progress = False

        if self.status_queue:
            self.status_queue.put(("STATUS", ("Disconnected", "red")))

    def _playwright_worker_loop(self):
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright library is not installed.")
            return

        with sync_playwright() as p:
            # 1. Connect to Port 9222 (Salesforce)
            browser_sf = None
            try:
                browser_sf = p.chromium.connect_over_cdp(f"http://127.0.0.1:{settings.cdp_ports.salesforce}")
                if browser_sf.contexts and browser_sf.contexts[0].pages:
                    self.salesforce.set_page(browser_sf.contexts[0].pages[0])
                logger.info("Connected to Salesforce CDP on port %d", settings.cdp_ports.salesforce)
            except Exception as e:
                logger.warning("Salesforce CDP connection skipped: %s", e)

            # 2. Connect to Port 9223 (Dialer & Outlook)
            browser_dialer = None
            context_dialer = None
            try:
                browser_dialer = p.chromium.connect_over_cdp(f"http://127.0.0.1:{settings.cdp_ports.dialer}")
                if browser_dialer.contexts:
                    context_dialer = browser_dialer.contexts[0]
                    if context_dialer.pages:
                        self.contaque.set_page(context_dialer.pages[0])
                logger.info("Connected to Dialer CDP on port %d", settings.cdp_ports.dialer)
            except Exception as e:
                logger.warning("Dialer CDP connection skipped: %s", e)

            self.is_connected = True
            if self.status_queue:
                self.status_queue.put(("STATUS", ("CDP Connected", "green")))

            # Command Processing & Status Polling Loop
            last_poll = 0.0

            while not self._stop_event.is_set():
                # Process pending commands from UI/Brain
                try:
                    cmd = self.playwright_queue.get_nowait()
                    action = cmd.get("action")

                    if action == "send_email" and context_dialer:
                        self.outreach.send_outlook_email(
                            browser_context=context_dialer,
                            recipient=cmd.get("recipient", ""),
                            subject=cmd.get("subject", ""),
                            body_text=cmd.get("body", "")
                        )
                    elif action == "disposition_salesforce":
                        self.salesforce.apply_disposition(
                            category=cmd.get("category", "NO_RESPONSE"),
                            notes=cmd.get("notes", "")
                        )
                except queue.Empty:
                    pass

                # Periodic Softphone Telephony Polling
                now = time.time()
                if now - last_poll > 1.0:
                    last_poll = now
                    sf_status = self.salesforce.get_softphone_status()

                    if sf_status == "INCALL" and not self.call_in_progress:
                        self.call_in_progress = True
                        lead_data = self.salesforce.scrape_active_lead()
                        if self.status_queue:
                            self.status_queue.put(("INCALL_DETECTED", lead_data))
                    elif sf_status == "IDLE" and self.call_in_progress:
                        self.call_in_progress = False

                time.sleep(0.1)

            # Cleanup handles on stop
            try:
                if browser_sf:
                    browser_sf.close()
                if browser_dialer:
                    browser_dialer.close()
            except Exception:
                pass


# Backward compatibility alias
SalesforceBot = CRMOrchestrator
