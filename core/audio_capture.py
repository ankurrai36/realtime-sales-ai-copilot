import time
import queue
import logging
import threading
from typing import List, Optional, Tuple, Callable
import numpy as np

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    import pyaudio

from config.settings import settings
from core.dsp import to_mono_safe, apply_smart_agc, resample_linear

logger = logging.getLogger(__name__)


class AudioCapturePipeline:
    """Multi-channel low-latency audio capture using Windows WASAPI loopback and microphone.
    
    Feeds processed PCM chunks to active streaming ASR sockets.
    """

    def __init__(self, on_packet_ready: Optional[Callable[[bytes], None]] = None):
        self.on_packet_ready = on_packet_ready
        self.is_capturing = False
        self.audio_gate_open = True

        self.pyaudio_instance: Optional[pyaudio.PyAudio] = None
        self.mic_stream = None
        self.loop_stream = None

        self.mic_queue: queue.Queue = queue.Queue(maxsize=settings.audio.buffer_queue_maxsize)
        self.loop_queue: queue.Queue = queue.Queue(maxsize=settings.audio.buffer_queue_maxsize)

        self._sender_thread: Optional[threading.Thread] = None
        self._target_rate = settings.audio.target_sample_rate
        self._chunk_ms = settings.audio.chunk_duration_ms

    def get_loopback_devices(self) -> List[Tuple[int, str]]:
        """Scans and lists active Windows WASAPI loopback audio renderers."""
        devices: List[Tuple[int, str]] = []
        p_temp = pyaudio.PyAudio()
        try:
            wasapi_info = p_temp.get_host_api_info_by_type(pyaudio.paWASAPI)
            for i in range(p_temp.get_device_count()):
                dev = p_temp.get_device_info_by_index(i)
                if dev.get("hostApi") == wasapi_info["index"] and dev.get("isLoopbackDevice"):
                    devices.append((int(dev["index"]), str(dev["name"])))
        except Exception as e:
            logger.error("Error enumerating WASAPI loopback endpoints: %s", e)
        finally:
            p_temp.terminate()

        return devices

    def set_audio_gate(self, is_open: bool):
        """Controls whether audio frames are broadcast or suppressed as comfort silence."""
        self.audio_gate_open = is_open
        state = "OPEN (Streaming audio)" if is_open else "CLOSED (Sending silence frames)"
        logger.info("Audio capture gate updated: %s", state)

    def _flush_queues(self):
        """Purges stale PCM chunks from buffer queues."""
        for q in (self.mic_queue, self.loop_queue):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break

    def start(self, loopback_device_index: int):
        """Starts multi-threaded audio capture pipeline."""
        if self.is_capturing:
            return

        self.is_capturing = True
        self.audio_gate_open = True
        self._flush_queues()

        self._sender_thread = threading.Thread(
            target=self._capture_and_dispatch_loop,
            args=(loopback_device_index,),
            name="AudioCapturePipelineWorker",
            daemon=True
        )
        self._sender_thread.start()
        logger.info("Audio capture pipeline activated on device index: %d", loopback_device_index)

    def stop(self):
        """Stops capturing and releases hardware stream handles."""
        self.is_capturing = False
        self._teardown_streams()

    def _teardown_streams(self):
        try:
            if self.mic_stream:
                self.mic_stream.stop_stream()
                self.mic_stream.close()
                self.mic_stream = None
            if self.loop_stream:
                self.loop_stream.stop_stream()
                self.loop_stream.close()
                self.loop_stream = None
            if self.pyaudio_instance:
                self.pyaudio_instance.terminate()
                self.pyaudio_instance = None
        except Exception as e:
            logger.debug("Hardware teardown exception (non-fatal): %s", e)

    def _stream_reader_worker(
        self,
        stream,
        src_rate: int,
        channels: int,
        target_queue: queue.Queue,
        is_customer: bool
    ):
        frames_per_chunk = max(1, int(src_rate * (self._chunk_ms / 1000.0)))

        while self.is_capturing:
            try:
                raw_bytes = stream.read(frames_per_chunk, exception_on_overflow=False)
                if not raw_bytes:
                    continue

                audio_arr = np.frombuffer(raw_bytes, dtype=np.int16)
                mono = to_mono_safe(audio_arr, channels)
                normalized = apply_smart_agc(
                    mono,
                    is_customer=is_customer,
                    target_rms=settings.audio.target_rms,
                    max_gain_customer=settings.audio.max_gain_customer,
                    max_gain_agent=settings.audio.max_gain_agent,
                    pre_emphasis_coef=settings.audio.pre_emphasis_coefficient
                )
                resampled = resample_linear(normalized, src_rate, self._target_rate)

                # Evict oldest frame if buffer approaches saturation
                if target_queue.qsize() > 5:
                    try:
                        target_queue.get_nowait()
                    except queue.Empty:
                        pass

                target_queue.put(resampled)
            except Exception:
                if self.is_capturing:
                    time.sleep(0.01)

    def _capture_and_dispatch_loop(self, loopback_idx: int):
        self._teardown_streams()
        self.pyaudio_instance = pyaudio.PyAudio()

        # 1. Initialize Microphone (Channel 0: Agent)
        try:
            mic_info = self.pyaudio_instance.get_default_input_device_info()
            mic_rate = int(mic_info["defaultSampleRate"])
            self.mic_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=mic_rate,
                input=True,
                input_device_index=mic_info["index"],
                frames_per_buffer=1024
            )
            threading.Thread(
                target=self._stream_reader_worker,
                args=(self.mic_stream, mic_rate, 1, self.mic_queue, False),
                name="MicReaderThread",
                daemon=True
            ).start()
            logger.info("Microphone initialized: %s (%d Hz)", mic_info.get("name"), mic_rate)
        except Exception as e:
            logger.warning("Microphone stream initialization failed: %s", e)

        # 2. Initialize WASAPI Loopback (Channel 1: Customer/Far-End)
        try:
            loop_info = self.pyaudio_instance.get_device_info_by_index(loopback_idx)
            loop_rate = int(loop_info["defaultSampleRate"])
            loop_channels = int(loop_info.get("maxInputChannels") or 2)
            self.loop_stream = self.pyaudio_instance.open(
                format=pyaudio.paInt16,
                channels=loop_channels,
                rate=loop_rate,
                input=True,
                input_device_index=loopback_idx,
                frames_per_buffer=1024
            )
            threading.Thread(
                target=self._stream_reader_worker,
                args=(self.loop_stream, loop_rate, loop_channels, self.loop_queue, True),
                name="LoopbackReaderThread",
                daemon=True
            ).start()
            logger.info("WASAPI Loopback stream initialized: %s (%d Hz, %d ch)", loop_info.get("name"), loop_rate, loop_channels)
        except Exception as e:
            logger.warning("WASAPI Loopback stream initialization failed: %s", e)

        # 3. Interleaving & Dispatch Loop
        target_frames = int(self._target_rate * (self._chunk_ms / 1000.0))

        def _normalize_chunk_len(chunk: np.ndarray) -> np.ndarray:
            if len(chunk) == target_frames:
                return chunk
            if len(chunk) > target_frames:
                return chunk[:target_frames]
            pad = np.zeros(target_frames, dtype=np.int16)
            pad[:len(chunk)] = chunk
            return pad

        try:
            while self.is_capturing:
                try:
                    agent_chunk = self.mic_queue.get(timeout=0.1)
                except queue.Empty:
                    agent_chunk = np.zeros(target_frames, dtype=np.int16)

                try:
                    customer_chunk = self.loop_queue.get(timeout=0.1)
                except queue.Empty:
                    customer_chunk = np.zeros(target_frames, dtype=np.int16)

                agent_aligned = _normalize_chunk_len(agent_chunk)
                customer_aligned = _normalize_chunk_len(customer_chunk)

                if not self.audio_gate_open:
                    stereo = np.zeros((target_frames * 2,), dtype=np.int16)
                else:
                    stereo = np.empty((target_frames * 2,), dtype=np.int16)
                    stereo[0::2] = agent_aligned       # Channel 0: Agent Mic
                    stereo[1::2] = customer_aligned    # Channel 1: Telephony / Customer

                packet = stereo.tobytes()

                if self.on_packet_ready and callable(self.on_packet_ready):
                    try:
                        self.on_packet_ready(packet)
                    except Exception as dispatch_err:
                        logger.error("Audio packet dispatch error: %s", dispatch_err)

        except Exception as e:
            logger.error("Audio capture master loop crashed: %s", e)
        finally:
            self._teardown_streams()
