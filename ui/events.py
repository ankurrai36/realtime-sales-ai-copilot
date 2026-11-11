import tkinter as tk
import logging
from typing import Any

logger = logging.getLogger(__name__)


def process_gui_events(app: Any):
    """Event pump polling status messages from background audio, transcription, and CDP workers."""
    try:
        while True:
            msg_data = app.status_queue.get_nowait()
            msg_type = msg_data[0]
            payload = msg_data[1]

            if msg_type == "STATUS":
                text, color_key = payload
                color_map = {
                    "red": "#e74c3c",
                    "green": "#00bc8c",
                    "blue": "#3498db",
                    "orange": "#f39c12"
                }
                hex_color = color_map.get(color_key, "#ffffff")
                app.status_label.config(text=f"Status: {text}", foreground=hex_color)

            elif msg_type == "TELEPHONY_STATE":
                app.telephony_label.config(text=f"Line State: {payload}")

            elif msg_type == "LEAD_DATA_SCRAPED":
                _display_lead_data(app, payload)

            elif msg_type == "CAPTION_UPDATE":
                _append_caption_to_transcript(app, payload)

            elif msg_type == "LIVE_COACHING_GROUNDED":
                _display_copilot_advice(app, payload)

            elif msg_type == "SALESFORCE_SUMMARY_GENERATED":
                _display_post_call_report(app, payload)

            elif msg_type == "GEMINI_STATUS":
                text, color = payload
                logger.info("[Brain Telemetry] %s", text)

    except Exception:
        pass
    finally:
        # Schedule next queue poll cycle
        app.root.after(80, lambda: process_gui_events(app))


def _display_lead_data(app: Any, lead_data: dict):
    try:
        app.lead_details_text.config(state="normal")
        app.lead_details_text.delete("1.0", tk.END)

        formatted = (
            f"Opportunity ID : {lead_data.get('opp_id', 'N/A')}\n"
            f"Prospect Name  : {lead_data.get('lead_name', 'N/A')}\n"
            f"Phone Number   : {lead_data.get('primary_phone', 'N/A')}\n"
            f"Email Address  : {lead_data.get('email', 'N/A')}\n"
            f"Current Stage  : {lead_data.get('stage', 'N/A')}\n"
            f"Target Program : {lead_data.get('program_name', 'N/A')}\n"
        )
        if lead_data.get("latest_notes") and lead_data.get("latest_notes") != "N/A":
            formatted += f"\nPrevious Notes:\n{lead_data.get('latest_notes')}\n"

        app.lead_details_text.insert(tk.END, formatted)
        app.lead_details_text.config(state="disabled")
    except Exception as e:
        logger.error("Failed displaying lead data in GUI: %s", e)


def _append_caption_to_transcript(app: Any, caption_payload: dict):
    try:
        text = caption_payload.get("text", "")
        speaker = caption_payload.get("speaker", "Unknown")

        tag = "agent" if any(k in speaker.lower() for k in ("me", "agent")) else "customer"

        app.transcript_text.insert(tk.END, f"[{speaker}]: ", tag)
        app.transcript_text.insert(tk.END, f"{text}\n")
        app.transcript_text.see(tk.END)
    except Exception as e:
        logger.error("Failed appending transcript line: %s", e)


def _display_copilot_advice(app: Any, advice_text: str):
    try:
        app.advisor_notes_input.delete("1.0", tk.END)
        app.advisor_notes_input.insert(tk.END, f"💡 REAL-TIME COPILOT SCRIPT:\n{advice_text}\n")
    except Exception as e:
        logger.error("Failed displaying copilot advice: %s", e)


def _display_post_call_report(app: Any, report_text: str):
    try:
        app.advisor_notes_input.insert(tk.END, f"\n\n========================================\n📋 POST-CALL 3-PART REPORT:\n{report_text}\n")
        app.advisor_notes_input.see(tk.END)
    except Exception as e:
        logger.error("Failed displaying post-call report: %s", e)
