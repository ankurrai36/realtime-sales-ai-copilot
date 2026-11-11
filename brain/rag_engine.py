import os
import re
import json
import time
import logging
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional

try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

from config.settings import settings
from brain.knowledge_loader import load_program_knowledge, load_prompts
from brain.database import (
    update_lead_history,
    update_lead_summaries,
    get_lead_history,
    get_lead_summaries
)

logger = logging.getLogger(__name__)


class SalesAIBrain:
    """Dynamic contextual RAG engine and real-time sales whisperer.
    
    Performs caller-voice separation, RAG context composition, objection handling
    injection, and seamless API key rotation on 429 rate limit exceptions.
    """

    def __init__(self, status_queue=None, playwright_queue=None):
        self.status_queue = status_queue
        self.playwright_queue = playwright_queue

        self.is_active = False
        self.live_history: List[Dict[str, str]] = []
        self.call_log: List[str] = []
        self.is_ai_thinking = False
        self.engine_busy_lock = False
        self.last_think_time = 0.0

        # Operational modes
        self.use_web_mode = False  # Toggle between Google GenAI SDK and CDP Web tab
        self.web_initialized_for_current_lead = False

        # Key rotation state
        self.api_keys = settings.gemini_api_keys
        self.current_key_index = 0
        self.api_lock = threading.Lock()
        self.gemini_client = None
        self.current_model = settings.gemini_default_model

        # Context state
        self.current_lead_context: Dict[str, Any] = {}
        self.current_program_key: Optional[str] = None
        self.historical_briefing_text: str = ""

        # Catalogs
        self.prompts_catalog: Dict[str, Any] = {}
        self.program_knowledge: Dict[str, Any] = {}

        self._init_client()
        self.refresh_knowledge_base()

    def _init_client(self):
        """Initializes or re-initializes the Google GenAI SDK client."""
        if not GENAI_AVAILABLE or not self.api_keys:
            self.gemini_client = None
            return

        with self.api_lock:
            active_key = self.api_keys[self.current_key_index % len(self.api_keys)]
            try:
                self.gemini_client = genai.Client(api_key=active_key)
                logger.info("GenAI client initialized with key index %d", self.current_key_index)
            except Exception as e:
                logger.error("Failed to initialize GenAI client: %s", e)
                self.gemini_client = None

    def rotate_key(self):
        """Rotates to next available API key upon hitting rate limits (HTTP 429)."""
        with self.api_lock:
            if not self.api_keys:
                return
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.warning("Gemini 429/Quota limit reached. Rotating to key index: %d", self.current_key_index)
            self._init_client()

    def refresh_knowledge_base(self):
        """Reloads playbooks, modular syllabus specs, and objection matrices from disk."""
        try:
            self.prompts_catalog = load_prompts()
            self.program_knowledge = load_program_knowledge()
            logger.info("RAG knowledge base refreshed: %d programs indexed.", len(self.program_knowledge))
        except Exception as e:
            logger.error("Knowledge base synchronization failed: %s", e)

    def _emit_status(self, message: str, color: str = "blue"):
        if self.status_queue:
            self.status_queue.put(("GEMINI_STATUS", (message, color)))

    def start_session(self, lead_context: Dict[str, Any], program_key: Optional[str] = None):
        """Prepares session state, retrieves past CRM summaries, and isolates call history."""
        self.is_active = True
        self.is_ai_thinking = False
        self.engine_busy_lock = False
        self.current_program_key = program_key
        self.web_initialized_for_current_lead = False

        self.current_lead_context = lead_context or {}
        opp_id = str(self.current_lead_context.get("opp_id", "N/A")).strip().upper()

        self.live_history = []
        self.call_log = [f"[{datetime.now().strftime('%H:%M:%S')}] 🟢 SESSION START (Opp ID: {opp_id})"]

        # Historical context synthesis
        self.historical_briefing_text = ""
        try:
            past_calls = get_lead_history(opp_id)
            past_summaries = get_lead_summaries(opp_id)

            if past_calls or past_summaries:
                lines = ["\n### RELEVANT HISTORICAL CRM CONTEXT ###\n"]
                if past_summaries:
                    lines.append("--- PREVIOUS AGENT NOTES ---")
                    for s in past_summaries:
                        lines.append(f"• {s}")
                if past_calls:
                    lines.append("\n--- PREVIOUS CALL TRANSCRIPTS ---")
                    for c in past_calls[-2:]:
                        lines.append(f"[{c.get('date')}]: {c.get('transcript')}\n")
                self.historical_briefing_text = "\n".join(lines)
        except Exception as e:
            logger.debug("Failed retrieving historical lead context: %s", e)

    def process_live_caption(self, text: str, speaker: str, is_final: bool):
        """Buffers finalized real-time captions into active dialogue history."""
        if is_final and text.strip():
            self.live_history.append({"speaker": speaker, "text": text})
            self.call_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {speaker}: {text}")

    def _get_customer_only_transcript(self) -> str:
        """Caller-Voice Gating: extracts strictly the customer's speech.
        
        Filters out 'Agent', 'Me', 'Me [EN]', 'Me [HI]' to eliminate model confusion
        and guarantee the AI only advises on what the prospect is stating.
        """
        filtered = []
        for entry in self.live_history:
            spk = str(entry.get("speaker", "")).strip().lower()
            if "agent" not in spk and "me" not in spk:
                filtered.append(f"[{entry['speaker']}]: {entry['text']}")

        if not filtered:
            return "(Waiting for customer speech input...)"
        return "\n".join(filtered)

    def generate_action_cue(self, use_google: bool = False, manual_notes: str = ""):
        """Triggers the real-time RAG pipeline to generate the next strategic talking script."""
        now = time.time()
        if self.engine_busy_lock:
            return
        if self.is_ai_thinking or (now - self.last_think_time < 0.8):
            return

        self.is_ai_thinking = True
        self.engine_busy_lock = True
        self.last_think_time = now

        threading.Thread(
            target=self._rag_pipeline_worker,
            args=(use_google, manual_notes),
            name="RAGPipelineWorker",
            daemon=True
        ).start()

    def _rag_pipeline_worker(self, use_google: bool, manual_notes: str):
        try:
            if self.status_queue:
                self.status_queue.put(("LIVE_COACHING_CLEAR", None))
            self._execute_rag_query(manual_notes, retry_count=0)
        finally:
            self._emit_status("Listening...", "green")
            self.is_ai_thinking = False
            self.engine_busy_lock = False

    def _execute_rag_query(self, manual_notes: str, retry_count: int = 0):
        try:
            customer_transcript = self._get_customer_only_transcript()

            # 1. Resolve Playbook via Fuzzy Match
            playbook_text = ""
            playbooks = self.prompts_catalog.get("playbooks", {})
            program_meta = self.program_knowledge.get(self.current_program_key, {})
            full_name = str(program_meta.get("program_name_full", "")).lower()
            clean_name = re.sub(r"[^a-z0-9]", " ", full_name)

            for p_key, p_val in playbooks.items():
                if p_key == "fallback_persona":
                    continue
                clean_key = re.sub(r"[^a-z0-9]", " ", p_key.lower())
                words = clean_key.split()
                if words and all(w in clean_name for w in words):
                    playbook_text = p_val.get("prompt", "")
                    break

            if not playbook_text:
                playbook_text = playbooks.get("fallback_persona", {}).get("prompt", "")

            # 2. Extract Structured Program Facts & Objection Tactics
            objection_tactics = json.dumps(program_meta.get("objection_handling", {}), indent=2, ensure_ascii=False)
            facts = json.dumps({
                "Modules": program_meta.get("detailed_modules", {}),
                "Fees & Installments": program_meta.get("fee_details", {}),
                "Eligibility": program_meta.get("eligibility", ""),
                "USPs": program_meta.get("sales_ammunition", {})
            }, indent=2, ensure_ascii=False)

            notes_block = f"\n### ADVISOR MANUAL DIRECTIVE (PRIORITY) ###\n{manual_notes}\n" if manual_notes else ""

            system_instruction = (
                f"{playbook_text}\n\n"
                f"### FACTUAL CURRICULUM CONTEXT (STRICT TRUTH SOURCE) ###\n{facts}\n\n"
                f"### OBJECTION RESOLUTION FRAMEWORKS ###\n{objection_tactics}\n"
                f"{notes_block}"
            )

            # Web route via CDP queue
            if self.use_web_mode and self.playwright_queue:
                self._emit_status("Synthesizing Web RAG...", "orange")
                payload = (
                    f"{system_instruction}\n"
                    f"{self.historical_briefing_text}\n\n"
                    f"### CALL TRANSCRIPT (CUSTOMER ONLY) ###\n{customer_transcript}\n\n"
                    "INSTRUCTION: Based on the facts and objection playbook, output ONLY the exact spoken words to reply."
                )
                self.playwright_queue.put({"action": "web_gemini_cue", "prompt": payload})
                return

            # API route via Google GenAI SDK
            self._emit_status("AI Brain Thinking...", "orange")
            full_prompt = (
                f"{system_instruction}\n\n"
                f"{self.historical_briefing_text}\n\n"
                f"### LIVE CUSTOMER SPEECH ###\n{customer_transcript}\n\n"
                "INSTRUCTION: Respond with ONLY the exact, punchy spoken script I should say right now."
            )

            if not self.gemini_client:
                raise RuntimeError("GenAI client is not configured or missing API keys.")

            config = types.GenerateContentConfig(temperature=0.3)
            response = self.gemini_client.models.generate_content(
                model=self.current_model,
                contents=full_prompt,
                config=config
            )
            script = response.text.strip().replace("[SCRIPT]", "").replace("[STRATEGY]", "").strip()
            if self.status_queue:
                self.status_queue.put(("LIVE_COACHING_GROUNDED", script))

        except Exception as e:
            logger.warning("RAG pipeline execution error (attempt %d): %s", retry_count, e)
            if self.api_keys and retry_count < len(self.api_keys):
                self.rotate_key()
                time.sleep(1.0)
                return self._execute_rag_query(manual_notes, retry_count + 1)
            self._emit_status("Generation Error", "red")

    def end_conversation_and_summarize(self):
        """Asynchronously produces the 3-part post-call analytical report."""
        self.is_active = False

        raw_transcript = "\n".join([f"[{m['speaker']}]: {m['text']}" for m in self.live_history])
        opp_id = str(self.current_lead_context.get("opp_id", "N/A")).strip().upper()

        if opp_id != "N/A" and raw_transcript.strip():
            update_lead_history(opp_id, raw_transcript)

        self._save_diagnostic_log()
        customer_transcript = self._get_customer_only_transcript()

        threading.Thread(
            target=self._post_call_synthesis_worker,
            args=(customer_transcript, opp_id),
            name="PostCallSynthesisWorker",
            daemon=True
        ).start()

    def _post_call_synthesis_worker(self, customer_transcript: str, opp_id: str):
        summary_prompt = (
            "You are an expert Sales Evaluation Director reviewing a completed consultation call.\n"
            "Based STRICTLY on the prospect's dialogue below, generate output with exactly these 3 sections:\n\n"
            "### 1. CRM SUMMARY ###\n"
            "- Core Experience, Objectives, Pain Points, and Objections expressed.\n"
            "- Concisely structured in natural bullet points. Never hallucinate unmentioned details.\n\n"
            "### 2. PERFORMANCE EVALUATION ###\n"
            "- Pain Points Uncovered: [Yes/No - Reason]\n"
            "- Objection Resolution: [Yes/No - Reason]\n"
            "- Solution Fit Alignment: [Yes/No - Reason]\n\n"
            "### 3. PERSONALIZED FOLLOW-UP EMAIL DRAFT ###\n"
            "Draft a concise, high-converting follow-up email reflecting the exact details discussed.\n\n"
            f"Customer Dialogue:\n{customer_transcript}"
        )

        try:
            if not self.gemini_client:
                raise RuntimeError("GenAI client unavailable.")

            response = self.gemini_client.models.generate_content(
                model=self.current_model,
                contents=summary_prompt
            )
            report = response.text.strip()
            if self.status_queue:
                self.status_queue.put(("SALESFORCE_SUMMARY_GENERATED", report))
                if opp_id != "N/A":
                    update_lead_summaries(opp_id, report)
        except Exception as e:
            logger.error("Failed generating post-call synthesis report: %s", e)
        finally:
            if self.status_queue:
                self.status_queue.put(("AI_SESSION_ENDED", None))

    def _save_diagnostic_log(self):
        """Dumps debug logs to logs/ directory."""
        if not self.call_log:
            return
        try:
            opp_id = str(self.current_lead_context.get("opp_id", "SESSION")).strip().upper()
            filename = f"call_log_{opp_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            dest = settings.logs_dir / filename
            with open(dest, "w", encoding="utf-8") as f:
                f.write(f"# Session Log: {opp_id}\n\n" + "\n".join(self.call_log) + "\n")
        except Exception as e:
            logger.debug("Failed saving diagnostic report: %s", e)


# Backward-compatible alias for existing imports
DualChatService = SalesAIBrain
