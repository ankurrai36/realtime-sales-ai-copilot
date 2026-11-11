import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False
    logger.warning("pycaw is not installed; audio session attenuation disabled.")


class AudioGovernor:
    """Controls Windows application volume sessions via Core Audio (PyCaw).
    
    Attenuates non-essential media applications during live inbound/outbound calls.
    """

    def __init__(self):
        self._last_state: Optional[bool] = None

    def set_media_volume(self, target_volume: float = 1.0, filter_processes: tuple = ("chrome.exe", "msedge.exe", "vlc.exe")):
        """Adjusts master volume for target media browser processes."""
        if not PYCAW_AVAILABLE:
            return

        try:
            sessions = AudioUtilities.GetAllSessions()
            for session in sessions:
                volume = session._ctl.QueryInterface(ISimpleAudioVolume)
                if session.Process and session.Process.name().lower() in filter_processes:
                    volume.SetMasterVolume(float(target_volume), None)
        except Exception as e:
            logger.debug("Failed to set process volume: %s", e)

    def duck_media(self):
        """Reduces background application audio during an active call."""
        self.set_media_volume(0.15)
        self._last_state = True

    def restore_media(self):
        """Restores background application audio once call concludes."""
        self.set_media_volume(1.0)
        self._last_state = False
