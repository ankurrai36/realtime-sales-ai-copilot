import json
import time
import socket
import logging
import threading
from typing import List, Optional, Callable
import websocket

from config.settings import settings

logger = logging.getLogger(__name__)


class DeepgramStreamingTranscriber:
    """Production streaming client for Deepgram Nova-2 with multichannel dual-language sockets

    Maintains dual persistent WebSockets (English-IN and Hindi) concurrently for real-time
    bilingual transcription with automatic failover key rotation and reconnect backoff.
    """

    DEEPGRAM_BASE_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(
        self,
        api_keys: Optional[List[str]] = None,
        on_transcript_callback: Optional[Callable[[str, str, bool], None]] = None
    ):
        self.api_keys: List[str] = api_keys if api_keys else settings.deepgram_api_keys
        self.on_transcript_callback = on_transcript_callback

        self.current_key_index: int = 0
        self.key_lock = threading.Lock()

        self.is_running: bool = False
        self.ws_en_connected: bool = False
        self.ws_hi_connected: bool = False

        self.ws_app_en: Optional[websocket.WebSocketApp] = None
        self.ws_app_hi: Optional[websocket.WebSocketApp] = None

    def get_active_key(self) -> str:
        with self.key_lock:
            if not self.api_keys:
                return ""
            return self.api_keys[self.current_key_index % len(self.api_keys)]

    def rotate_key(self) -> str:
        with self.key_lock:
            if not self.api_keys:
                return ""
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            active_key = self.api_keys[self.current_key_index]
            masked_key = f"{active_key[:4]}...{active_key[-4:]}" if len(active_key) > 8 else "***"
            logger.warning("Deepgram API quota exhausted or rejected. Rotated to key index %d (%s)", self.current_key_index, masked_key)
            return active_key

    def check_network(self, host: str = "api.deepgram.com", port: int = 443, timeout: float = 3.0) -> bool:
        """Probes TCP handshake to confirm outbound WAN reachability before reconnecting."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def start(self):
        """Spawns dual language transcription threads."""
        if self.is_running:
            return

        if not self.api_keys:
            logger.error("Cannot start Deepgram transcriber: No API keys configured in environment.")
            return

        self.is_running = True
        self.ws_en_connected = False
        self.ws_hi_connected = False

        threading.Thread(
            target=self._run_socket_worker,
            args=("en-IN", "en"),
            name="DeepgramSocket-EN",
            daemon=True
        ).start()

        threading.Thread(
            target=self._run_socket_worker,
            args=("hi", "hi"),
            name="DeepgramSocket-HI",
            daemon=True
        ).start()

        logger.info("Deepgram dual streaming listeners spawned.")

    def stop(self):
        """Gracefully disconnects both WebSockets."""
        self.is_running = False
        if self.ws_app_en:
            try:
                self.ws_app_en.close()
            except Exception:
                pass
        if self.ws_app_hi:
            try:
                self.ws_app_hi.close()
            except Exception:
                pass
        self.ws_en_connected = False
        self.ws_hi_connected = False

    def dispatch_audio_frame(self, frame_bytes: bytes):
        """Distributes raw linear16 stereo PCM chunks to all connected language sockets."""
        if not self.is_running or not frame_bytes:
            return

        if self.ws_en_connected and self.ws_app_en:
            try:
                self.ws_app_en.send(frame_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                pass

        if self.ws_hi_connected and self.ws_app_hi:
            try:
                self.ws_app_hi.send(frame_bytes, opcode=websocket.ABNF.OPCODE_BINARY)
            except Exception:
                pass

    def _build_stream_url(self, language: str) -> str:
        params = [
            "encoding=linear16",
            "sample_rate=16000",
            "channels=2",
            "multichannel=true",
            "model=nova-2",
            f"language={language}",
            "smart_format=true",
            "endpointing=500",
            "filler_words=true",
            "keepalive=true"
        ]
        return f"{self.DEEPGRAM_BASE_URL}?{'&'.join(params)}"

    def _run_socket_worker(self, language_code: str, stream_id: str):
        url = self._build_stream_url(language_code)

        def on_message(ws, raw_message):
            try:
                msg = json.loads(raw_message)
                if msg.get("type") == "Results":
                    is_final = msg.get("is_final", False)
                    if is_final:
                        channel_idx = msg.get("channel_index", [0])[0]
                        # Channel 0: Agent Mic; Channel 1: Telephony / Customer
                        speaker = f"Me [{stream_id.upper()}]" if channel_idx == 0 else f"Customer [{stream_id.upper()}]"
                        alternatives = msg.get("channel", {}).get("alternatives", [])
                        if alternatives:
                            transcript = alternatives[0].get("transcript", "").strip()
                            if transcript and self.on_transcript_callback:
                                self.on_transcript_callback(transcript, speaker, is_final)
            except Exception as parse_err:
                logger.debug("Failed parsing Deepgram payload: %s", parse_err)

        def on_error(ws, error):
            err_str = str(error)
            logger.warning("Deepgram [%s] error: %s", stream_id, err_str)
            if any(code in err_str for code in ("401", "402", "403", "Handshake status")):
                self.rotate_key()
                try:
                    ws.close()
                except Exception:
                    pass

        def on_open(ws):
            if stream_id == "en":
                self.ws_en_connected = True
            else:
                self.ws_hi_connected = True
            logger.info("Deepgram [%s] WebSocket stream opened successfully.", stream_id)

        def on_close(ws, close_status, close_msg):
            if stream_id == "en":
                self.ws_en_connected = False
            else:
                self.ws_hi_connected = False
            logger.debug("Deepgram [%s] stream closed: %s - %s", stream_id, close_status, close_msg)

        while self.is_running:
            if not self.check_network():
                time.sleep(3.0)
                continue

            current_key = self.get_active_key()
            if not current_key:
                time.sleep(2.0)
                continue

            ws_instance = websocket.WebSocketApp(
                url,
                header=[f"Authorization: Token {current_key}"],
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            if stream_id == "en":
                self.ws_app_en = ws_instance
            else:
                self.ws_app_hi = ws_instance

            try:
                ws_instance.run_forever(ping_interval=20, ping_timeout=15)
            except Exception as ws_err:
                logger.error("WebSocket run error on [%s]: %s", stream_id, ws_err)

            time.sleep(1.5)
