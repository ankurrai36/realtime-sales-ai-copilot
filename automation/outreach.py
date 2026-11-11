import time
import logging
import requests
import threading
import urllib.parse
from typing import Optional, Tuple, Dict, Any

from config.settings import settings

logger = logging.getLogger(__name__)


class OutreachDispatcher:
    """Dispatches omnichannel communications (SMS, WhatsApp, Outlook Email) via webhooks and CDP."""

    def __init__(self, bot_interface=None):
        self.bot_interface = bot_interface

    def _sanitize_phone(self, raw_phone: str) -> Optional[str]:
        if not raw_phone or raw_phone == "N/A":
            return None
        digits = "".join(filter(str.isdigit, str(raw_phone)))
        if len(digits) == 10:
            return "91" + digits
        elif len(digits) >= 10:
            return digits
        return None

    def send_sms(self, phone_number: str, message_text: str) -> bool:
        """Dispatches SMS payload via configured mobile trigger webhook."""
        clean_phone = self._sanitize_phone(phone_number)
        if not clean_phone:
            logger.warning("SMS aborted: invalid phone number '%s'", phone_number)
            return False

        device_id = settings.macrodroid_device_id
        webhook_url = settings.macrodroid_webhook_url

        if not webhook_url and device_id:
            encoded_msg = urllib.parse.quote(message_text)
            webhook_url = f"https://trigger.macrodroid.com/{device_id}/send_sms?number={clean_phone}&msg={encoded_msg}"

        if not webhook_url or "REPLACE" in webhook_url:
            logger.info("SMS mock dispatch to %s: %s", clean_phone, message_text[:60])
            return True

        try:
            resp = requests.get(webhook_url, timeout=6.0)
            success = resp.status_code == 200
            if success:
                logger.info("SMS webhook acknowledged for %s", clean_phone)
            return success
        except Exception as e:
            logger.error("SMS webhook dispatch failed: %s", e)
            return False

    def send_whatsapp(self, phone_number: str, message_text: str) -> bool:
        """Dispatches WhatsApp template message via mobile automation gateway."""
        clean_phone = self._sanitize_phone(phone_number)
        if not clean_phone:
            logger.warning("WhatsApp aborted: invalid phone number '%s'", phone_number)
            return False

        device_id = settings.macrodroid_device_id
        if not device_id or "REPLACE" in str(device_id):
            logger.info("WhatsApp mock dispatch to %s: %s", clean_phone, message_text[:60])
            return True

        encoded_msg = urllib.parse.quote(message_text)
        url = f"https://trigger.macrodroid.com/{device_id}/send_wa?number={clean_phone}&msg={encoded_msg}"

        try:
            resp = requests.get(url, timeout=6.0)
            return resp.status_code == 200
        except Exception as e:
            logger.error("WhatsApp gateway dispatch error: %s", e)
            return False

    def send_outlook_email(self, browser_context: Any, recipient: str, subject: str, body_text: str) -> bool:
        """Automates Outlook Web email creation and dispatch inside Port 9223 browser context."""
        if not browser_context or not recipient:
            return False

        try:
            page = None
            for p in browser_context.pages:
                url_low = p.url.lower()
                if any(domain in url_low for domain in ("outlook.cloud.microsoft", "outlook.office.com", "outlook.live.com")):
                    page = p
                    break

            if not page:
                page = browser_context.new_page()
                page.goto("https://outlook.office.com/mail/", wait_until="commit")

            page.bring_to_front()
            time.sleep(0.5)

            # Trigger New Mail
            new_mail_btn = page.locator("button[aria-label='New mail'], button:has-text('New mail')").first
            new_mail_btn.click(timeout=5000)
            time.sleep(1.0)

            # Fill recipient
            to_field = page.locator("div[role='combobox'][aria-label*='To' i], input[aria-label*='To' i]").first
            to_field.fill(recipient)
            page.keyboard.press("Enter")

            # Fill subject
            subj_field = page.locator("input[placeholder*='Add a subject' i], input[aria-label*='Subject' i]").first
            subj_field.fill(subject)

            # Inject Body and Signature
            formatted_body = body_text.replace("\n", "<br>")
            sig_html = f"""
            <div style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
                {formatted_body}<br><br>
                Regards,<br>
                <b>{settings.identity.advisor_name}</b><br>
                <b>E:</b> <a href="mailto:{settings.identity.advisor_email}">{settings.identity.advisor_email}</a><br>
                <b>M:</b> {settings.identity.advisor_phone}<br>
                <a href="{settings.identity.portal_url}">{settings.identity.organization_name}</a>
            </div>
            """
            page.evaluate(
                "(html) => { const el = document.querySelector('div[aria-label=\"Message body\"]'); if (el) el.innerHTML = html; }",
                sig_html
            )
            time.sleep(0.8)

            # Dispatch Send
            send_btn = page.locator("button[aria-label='Send'], button[title='Send']").first
            send_btn.click(timeout=4000)
            logger.info("Outlook email successfully sent to %s", recipient)
            return True

        except Exception as e:
            logger.error("Outlook Web email dispatch failed for %s: %s", recipient, e)
            return False
