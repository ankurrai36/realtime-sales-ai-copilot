import sys
import queue
import logging
import tkinter as tk
from typing import Dict, Any

try:
    from ttkbootstrap import Style
    TTKBOOTSTRAP_AVAILABLE = True
except ImportError:
    TTKBOOTSTRAP_AVAILABLE = False

from config.settings import settings, configure_logging
from core.audio_capture import AudioCapturePipeline
from core.audio_governor import AudioGovernor
from transcription.caption_processor import CaptionProcessor
from transcription.deepgram_client import DeepgramStreamingTranscriber
from brain.rag_engine import SalesAIBrain
from automation.crm_orchestrator import CRMOrchestrator
from ui.components import build_workstation_ui
from ui.events import process_gui_events

logger = logging.getLogger(__name__)


class SalesCopilotWorkstationApp:
    """Main workstation application managing UI event loop and hardware thread bindings."""

    def __init__(self):
        configure_logging()
        logger.info("Initializing Sales Copilot Workstation...")

        # 1. UI Root Window
        if TTKBOOTSTRAP_AVAILABLE:
            self.style = Style(theme="superhero")
            self.root = self.style.master
        else:
            self.root = tk.Tk()

        # 2. Inter-Thread Communication Queues
        self.status_queue: queue.Queue = queue.Queue()
        self.playwright_queue: queue.Queue = queue.Queue()

        # 3. State Containers
        self.current_lead_data: Dict[str, Any] = {}
        self.sheet_manager = None

        # 4. Initialize Core Processing Clients
        self.caption_processor = CaptionProcessor(status_queue=self.status_queue)
        self.brain = SalesAIBrain(
            status_queue=self.status_queue,
            playwright_queue=self.playwright_queue
        )
        self.audio_governor = AudioGovernor()

        # 5. Transcription Client (Dual-Socket Deepgram Nova-2)
        self.transcriber = DeepgramStreamingTranscriber(
            on_transcript_callback=self._handle_raw_transcript
        )

        # 6. Audio Acquisition Pipeline (WASAPI Loopback + Mic)
        self.audio_pipeline = AudioCapturePipeline(
            on_packet_ready=self.transcriber.dispatch_audio_frame
        )

        # 7. Browser CRM Orchestrator (CDP)
        self.orchestrator = CRMOrchestrator(
            gui_app=self,
            status_queue=self.status_queue,
            playwright_queue=self.playwright_queue
        )

        # 8. Render Workstation GUI
        build_workstation_ui(self)

        # 9. Enumerate Audio Hardware
        devices = self.audio_pipeline.get_loopback_devices()
        dev_names = [f"{idx}: {name}" for idx, name in devices]
        self.audio_device_combo["values"] = dev_names
        if dev_names:
            self.audio_device_combo.set(dev_names[0])

        # 10. Bind Window Protocol and Event Loop
        self.root.protocol("WM_DELETE_WINDOW", self.on_shutdown)
        self.root.after(100, lambda: process_gui_events(self))

    def _handle_raw_transcript(self, text: str, speaker: str, is_final: bool):
        """Callback executed by Deepgram client upon receiving speech results."""
        self.caption_processor.process_caption_update({
            "text": text,
            "speaker": speaker,
            "is_final": is_final
        })
        self.brain.process_live_caption(text=text, speaker=speaker, is_final=is_final)
        self.status_queue.put(("CAPTION_UPDATE", {
            "text": text,
            "speaker": speaker,
            "is_final": is_final
        }))

    def on_shutdown(self):
        """Performs clean thread termination and hardware release before closing."""
        logger.info("Workstation shutdown initiated...")
        try:
            self.audio_pipeline.stop()
            self.transcriber.stop()
            self.orchestrator.stop_and_disconnect()
        except Exception as e:
            logger.debug("Shutdown exception (non-fatal): %s", e)
        finally:
            self.root.destroy()
            sys.exit(0)

    def run(self):
        self.root.mainloop()
