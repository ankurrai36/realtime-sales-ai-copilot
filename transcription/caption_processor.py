import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CaptionProcessor:
    """Manages raw caption streams, speaker transitions, and transcript history buffers.
    
    Fully decoupled from presentation tier; communicates purely through event queues and models.
    """

    def __init__(self, status_queue=None):
        self.status_queue = status_queue
        self.current_session_text: List[Dict[str, str]] = []
        self.last_speaker: Optional[str] = None
        self.session_start_time: Optional[datetime] = None

    def start_session(self):
        """Initializes a new session transcript buffer."""
        self.current_session_text = []
        self.last_speaker = None
        self.session_start_time = datetime.now()
        logger.info("Session caption buffer initialized.")

    def process_caption_update(self, data: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Processes and filters incoming ASR caption payloads."""
        try:
            text = str(data.get("text", "")).strip()
            speaker = str(data.get("speaker", "Unknown"))
            is_final = bool(data.get("is_final", False))

            if not text:
                return None

            if is_final:
                if speaker != self.last_speaker:
                    self.last_speaker = speaker

                entry = {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "speaker": speaker,
                    "text": text
                }
                self.current_session_text.append(entry)

                return {
                    "formatted": f"[{speaker}]: {text}",
                    "raw": text,
                    "speaker": speaker
                }

        except Exception as e:
            logger.error("Caption normalization error: %s", e)

        return None

    def get_full_transcript(self) -> str:
        """Serializes current session dialogue into timestamped transcript text."""
        return "\n".join([
            f"[{entry['timestamp']}] {entry['speaker']}: {entry['text']}"
            for entry in self.current_session_text
        ])

    def clear_session(self):
        """Wipes active session buffers."""
        self.current_session_text = []
        self.last_speaker = None
