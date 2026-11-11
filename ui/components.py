import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Any

from config.settings import settings


def build_workstation_ui(app: Any):
    """Constructs the high-density professional sales advisor workstation layout."""
    app.root.title("Real-Time Sales AI Copilot & CRM Orchestrator")
    app.root.geometry("1400x900")
    app.root.minsize(1100, 750)

    paned = ttk.PanedWindow(app.root, orient=tk.HORIZONTAL)
    paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    # 1. Left Control Column
    left_frame = ttk.Frame(paned, width=440)
    paned.add(left_frame, weight=1)

    # 2. Right Analytical & Transcription Column
    right_frame = ttk.Frame(paned)
    paned.add(right_frame, weight=3)

    # Left Column Layout
    _build_status_panel(app, left_frame)
    _build_controls_panel(app, left_frame)
    _build_sheet_campaign_panel(app, left_frame)
    _build_disposition_panel(app, left_frame)
    _build_quick_outreach_panel(app, left_frame)
    _build_lead_details_panel(app, left_frame)

    # Right Column Layout
    _build_settings_bar(app, right_frame)
    _build_transcript_panel(app, right_frame)
    _build_copilot_notes_panel(app, right_frame)
    _build_action_bar(app, right_frame)


def _build_status_panel(app: Any, parent: ttk.Frame):
    frame = ttk.LabelFrame(parent, text="System & Telephony Telemetry")
    frame.pack(fill="x", padx=4, pady=3)

    app.status_label = ttk.Label(
        frame,
        text="Status: Standby (Disconnected)",
        font=("Segoe UI", 10, "bold"),
        foreground="#e74c3c"
    )
    app.status_label.pack(anchor="w", padx=8, pady=2)

    app.telephony_label = ttk.Label(
        frame,
        text="Line State: IDLE",
        font=("Segoe UI", 9),
        foreground="#95a5a6"
    )
    app.telephony_label.pack(anchor="w", padx=8, pady=2)


def _build_controls_panel(app: Any, parent: ttk.Frame):
    from ui import actions

    frame = ttk.LabelFrame(parent, text="Hardware & Automation Controls")
    frame.pack(fill="x", padx=4, pady=3)

    row1 = ttk.Frame(frame)
    row1.pack(fill="x", padx=6, pady=2)

    app.btn_connect_cdp = ttk.Button(
        row1,
        text="Attach CDP Ports (9222-9224)",
        command=lambda: actions.attach_cdp_browsers(app),
        style="primary.TButton"
    )
    app.btn_connect_cdp.pack(side="left", expand=True, fill="x", padx=2)

    app.btn_toggle_audio = ttk.Button(
        row1,
        text="Start ASR Pipeline",
        command=lambda: actions.toggle_audio_capture(app),
        style="success.TButton"
    )
    app.btn_toggle_audio.pack(side="left", expand=True, fill="x", padx=2)

    row2 = ttk.Frame(frame)
    row2.pack(fill="x", padx=6, pady=2)

    app.btn_kill_switch = ttk.Button(
        row2,
        text="Emergency Kill Switch",
        command=lambda: actions.emergency_kill(app),
        style="danger.TButton"
    )
    app.btn_kill_switch.pack(side="left", expand=True, fill="x", padx=2)


def _build_sheet_campaign_panel(app: Any, parent: ttk.Frame):
    from ui import actions

    frame = ttk.LabelFrame(parent, text="Batch Campaign Feeder")
    frame.pack(fill="x", padx=4, pady=3)

    top_row = ttk.Frame(frame)
    top_row.pack(fill="x", padx=6, pady=2)

    app.btn_load_sheet = ttk.Button(
        top_row,
        text="Load Lead Sheet (.xlsx, .csv)",
        command=lambda: actions.load_sheet_dialog(app)
    )
    app.btn_load_sheet.pack(side="left", expand=True, fill="x", padx=2)

    app.sheet_progress_label = ttk.Label(top_row, text="No active batch", font=("Segoe UI", 9))
    app.sheet_progress_label.pack(side="right", padx=4)


def _build_disposition_panel(app: Any, parent: ttk.Frame):
    from ui import actions

    frame = ttk.LabelFrame(parent, text="Rapid CRM Disposition")
    frame.pack(fill="x", padx=4, pady=3)

    grid = ttk.Frame(frame)
    grid.pack(fill="x", padx=6, pady=4)

    disps = [
        ("No Response", "NO_RESPONSE", "secondary.TButton"),
        ("Call Back", "CALL_BACK", "info.TButton"),
        ("Warm Lead", "WARM", "warning.TButton"),
        ("Not Interested", "NOT_INTERESTED", "dark.TButton")
    ]

    for idx, (lbl, code, sty) in enumerate(disps):
        btn = ttk.Button(
            grid,
            text=lbl,
            command=lambda c=code: actions.submit_disposition(app, c),
            style=sty
        )
        btn.grid(row=idx // 2, column=idx % 2, padx=3, pady=2, sticky="ew")

    grid.columnconfigure(0, weight=1)
    grid.columnconfigure(1, weight=1)


def _build_quick_outreach_panel(app: Any, parent: ttk.Frame):
    from ui import actions

    frame = ttk.LabelFrame(parent, text="Omnichannel Outreach Channels")
    frame.pack(fill="x", padx=4, pady=3)

    row = ttk.Frame(frame)
    row.pack(fill="x", padx=6, pady=3)

    app.btn_send_wa = ttk.Button(
        row,
        text="WhatsApp Brochure",
        command=lambda: actions.quick_send_whatsapp(app)
    )
    app.btn_send_wa.pack(side="left", expand=True, fill="x", padx=2)

    app.btn_send_sms = ttk.Button(
        row,
        text="Follow-up SMS",
        command=lambda: actions.quick_send_sms(app)
    )
    app.btn_send_sms.pack(side="left", expand=True, fill="x", padx=2)

    app.btn_send_email = ttk.Button(
        row,
        text="Outlook Email",
        command=lambda: actions.quick_send_email(app)
    )
    app.btn_send_email.pack(side="left", expand=True, fill="x", padx=2)


def _build_lead_details_panel(app: Any, parent: ttk.Frame):
    frame = ttk.LabelFrame(parent, text="Active Prospect Metadata")
    frame.pack(fill="both", expand=True, padx=4, pady=3)

    app.lead_details_text = scrolledtext.ScrolledText(
        frame,
        wrap=tk.WORD,
        height=8,
        font=("Segoe UI", 9),
        bg="#2b3e50",
        fg="#ecf0f1",
        insertbackground="white"
    )
    app.lead_details_text.pack(fill="both", expand=True, padx=6, pady=4)
    app.lead_details_text.insert(tk.END, "Awaiting lead sync from CRM or dialer...")
    app.lead_details_text.config(state="disabled")


def _build_settings_bar(app: Any, parent: ttk.Frame):
    bar = ttk.Frame(parent)
    bar.pack(fill="x", padx=4, pady=3)

    # Audio Device Loopback Selector
    ttk.Label(bar, text="WASAPI Loopback:").pack(side="left", padx=4)
    app.audio_device_combo = ttk.Combobox(bar, state="readonly", width=38)
    app.audio_device_combo.pack(side="left", padx=4)

    # Model Selector
    ttk.Label(bar, text="AI Model:").pack(side="left", padx=(12, 4))
    app.model_combo = ttk.Combobox(
        bar,
        values=settings.gemini_fallback_models,
        state="readonly",
        width=18
    )
    app.model_combo.set(settings.gemini_default_model)
    app.model_combo.pack(side="left", padx=4)

    # Target Program Dropdown
    ttk.Label(bar, text="Playbook:").pack(side="left", padx=(12, 4))
    app.program_combo = ttk.Combobox(bar, state="readonly", width=26)
    app.program_combo.pack(side="left", padx=4)


def _build_transcript_panel(app: Any, parent: ttk.Frame):
    frame = ttk.LabelFrame(parent, text="Dual-Channel Real-Time Conversation Stream")
    frame.pack(fill="both", expand=True, padx=4, pady=3)

    app.transcript_text = scrolledtext.ScrolledText(
        frame,
        wrap=tk.WORD,
        height=14,
        font=("Consolas", 10),
        bg="#1e2b37",
        fg="#ecf0f1",
        insertbackground="white"
    )
    app.transcript_text.pack(fill="both", expand=True, padx=6, pady=4)

    # Speaker tag coloring
    app.transcript_text.tag_config("agent", foreground="#00bc8c", font=("Consolas", 10, "bold"))
    app.transcript_text.tag_config("customer", foreground="#3498db", font=("Consolas", 10))
    app.transcript_text.tag_config("system", foreground="#f39c12", font=("Consolas", 9, "italic"))


def _build_copilot_notes_panel(app: Any, parent: ttk.Frame):
    frame = ttk.LabelFrame(parent, text="Contextual RAG Copilot & Advisor Directives")
    frame.pack(fill="both", expand=True, padx=4, pady=3)

    app.advisor_notes_input = scrolledtext.ScrolledText(
        frame,
        wrap=tk.WORD,
        height=7,
        font=("Segoe UI", 10),
        bg="#2c3e50",
        fg="#ffffff",
        insertbackground="white"
    )
    app.advisor_notes_input.pack(fill="both", expand=True, padx=6, pady=4)
    app.advisor_notes_input.insert(tk.END, "Copilot suggestions and talking points will stream here live during the call...")


def _build_action_bar(app: Any, parent: ttk.Frame):
    from ui import actions

    bar = ttk.Frame(parent)
    bar.pack(fill="x", padx=4, pady=4)

    app.btn_ai_cue = ttk.Button(
        bar,
        text="Generate AI Strategic Cue",
        command=lambda: actions.trigger_ai_cue(app),
        style="warning.TButton"
    )
    app.btn_ai_cue.pack(side="left", expand=True, fill="x", padx=4)

    app.btn_finalize = ttk.Button(
        bar,
        text="Finalize Call & Synthesize 3-Part Report",
        command=lambda: actions.finalize_call(app),
        style="success.TButton"
    )
    app.btn_finalize.pack(side="left", expand=True, fill="x", padx=4)

    app.btn_clear_transcript = ttk.Button(
        bar,
        text="Clear Screen",
        command=lambda: actions.clear_transcript_view(app),
        style="secondary.TButton"
    )
    app.btn_clear_transcript.pack(side="right", padx=4)
