import os
import tkinter as tk
from tkinter import messagebox, filedialog
import logging
from typing import Any

from automation.browser_launcher import launch_cdp_browser_instances
from automation.sheet_campaign import SheetCampaignManager
from config.settings import settings

logger = logging.getLogger(__name__)


def attach_cdp_browsers(app: Any):
    """Launches or connects to remote debugging browser endpoints."""
    app.status_queue.put(("STATUS", ("Connecting to CDP...", "orange")))
    results = launch_cdp_browser_instances()
    app.orchestrator.start_orchestrator()
    connected_count = sum(1 for v in results.values() if v)
    app.status_queue.put(("STATUS", (f"CDP Linked ({connected_count}/3 ports)", "green")))


def toggle_audio_capture(app: Any):
    """Starts or halts the WASAPI loopback + microphone ASR pipeline."""
    if not app.audio_pipeline.is_capturing:
        selected_dev = app.audio_device_combo.get()
        if not selected_dev:
            messagebox.showwarning("Device Selection", "Please select a WASAPI Loopback device first.")
            return

        try:
            dev_idx = int(selected_dev.split(":")[0])
        except Exception:
            dev_idx = 0

        # Start Deepgram sockets and capture thread
        app.transcriber.start()
        app.audio_pipeline.start(loopback_device_index=dev_idx)
        app.btn_toggle_audio.config(text="Stop ASR Pipeline", style="danger.TButton")
        app.status_queue.put(("STATUS", ("ASR Live (Capturing Dual-Stream)", "green")))
    else:
        app.audio_pipeline.stop()
        app.transcriber.stop()
        app.btn_toggle_audio.config(text="Start ASR Pipeline", style="success.TButton")
        app.status_queue.put(("STATUS", ("ASR Standby", "blue")))


def emergency_kill(app: Any):
    """Triggers global kill switch halting all audio and CDP routines."""
    app.audio_pipeline.stop()
    app.transcriber.stop()
    app.orchestrator.stop_and_disconnect()
    app.btn_toggle_audio.config(text="Start ASR Pipeline", style="success.TButton")
    app.status_queue.put(("STATUS", ("System Terminated via Kill Switch", "red")))


def load_sheet_dialog(app: Any):
    """Prompts file dialog to load .xlsx or .csv campaign leads."""
    file_path = filedialog.askopenfilename(
        title="Select Lead Campaign Sheet",
        filetypes=[("Spreadsheet Files", "*.xlsx *.csv *.xlsm"), ("All Files", "*.*")]
    )
    if not file_path:
        return

    manager = SheetCampaignManager(file_path)
    if manager.total_leads > 0:
        app.sheet_manager = manager
        app.orchestrator.sheet_manager = manager
        app.sheet_progress_label.config(text=f"Batch: {manager.total_leads} leads ({os.path.basename(file_path)})")
        messagebox.showinfo("Campaign Loaded", f"Successfully loaded {manager.total_leads} prospect records.")
    else:
        messagebox.showerror("Load Failed", "Could not parse valid lead records from selected file.")


def submit_disposition(app: Any, category: str):
    """Submits wrap-up disposition code to CRM via Playwright."""
    app.orchestrator.playwright_queue.put({
        "action": "disposition_salesforce",
        "category": category,
        "notes": f"Automated wrap-up disposition: {category}"
    })
    app.status_queue.put(("STATUS", (f"Disposition Sent: {category}", "blue")))


def quick_send_whatsapp(app: Any):
    """Sends default program brochure to prospect's WhatsApp."""
    phone = app.current_lead_data.get("primary_phone")
    if not phone or phone == "N/A":
        messagebox.showwarning("Outreach", "No active phone number available for outreach.")
        return

    prog = app.current_lead_data.get("program_name", "Executive Program")
    msg = f"Hello, sharing the curriculum brochure for the {prog}. Let us know your availability to discuss your application."
    app.orchestrator.outreach.send_whatsapp(phone, msg)
    messagebox.showinfo("WhatsApp", f"WhatsApp payload dispatched for {phone}.")


def quick_send_sms(app: Any):
    """Sends SMS template follow-up."""
    phone = app.current_lead_data.get("primary_phone")
    if not phone or phone == "N/A":
        messagebox.showwarning("Outreach", "No active phone number available for outreach.")
        return

    prog = app.current_lead_data.get("program_name", "Executive Program")
    msg = f"Hi, tried connecting regarding the {prog}. Please let us know a convenient time to reconnect today."
    app.orchestrator.outreach.send_sms(phone, msg)
    messagebox.showinfo("SMS", f"SMS dispatched for {phone}.")


def quick_send_email(app: Any):
    """Submits email dispatch task to Outlook queue."""
    email = app.current_lead_data.get("email")
    if not email or email == "N/A":
        messagebox.showwarning("Outreach", "No active prospect email address found.")
        return

    prog = app.current_lead_data.get("program_name", "Executive Program")
    app.orchestrator.playwright_queue.put({
        "action": "send_email",
        "recipient": email,
        "subject": f"Information regarding {prog}",
        "body": f"Dear Candidate,\n\nFollowing up regarding your interest in the {prog}. Please review the curriculum details on our portal and let us know if you have any questions.\n"
    })
    messagebox.showinfo("Email", f"Email task queued for {email}.")


def trigger_ai_cue(app: Any):
    """Requests on-demand real-time coaching cue from RAG engine."""
    manual_notes = app.advisor_notes_input.get("1.0", tk.END).strip()
    app.brain.generate_action_cue(manual_notes=manual_notes)


def finalize_call(app: Any):
    """Wraps up call, triggers post-call synthesis, and saves transcript."""
    app.brain.end_conversation_and_summarize()
    app.status_queue.put(("STATUS", ("Synthesizing 3-Part Post-Call Report...", "orange")))


def clear_transcript_view(app: Any):
    app.transcript_text.delete("1.0", tk.END)
