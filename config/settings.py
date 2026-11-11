import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv

# Base directory for the repository root
BASE_DIR: Path = Path(__file__).resolve().parent.parent

# Load local environment configuration (.env)
ENV_PATH: Path = BASE_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH)


@dataclass
class AudioPipelineConfig:
    target_sample_rate: int = 16000
    chunk_duration_ms: int = 40
    target_rms: float = 0.28
    max_gain_customer: float = 20.0
    max_gain_agent: float = 1.2
    pre_emphasis_coefficient: float = 0.85
    buffer_queue_maxsize: int = 100


@dataclass
class CDPPortConfig:
    salesforce: int = int(os.getenv("CRM_PORT_SALESFORCE", "9222"))
    dialer: int = int(os.getenv("CRM_PORT_DIALER", "9223"))
    ai_studio: int = int(os.getenv("CRM_PORT_AISTUDIO", "9224"))


@dataclass
class IdentityConfig:
    advisor_name: str = os.getenv("ADVISOR_NAME", "Senior Admissions Advisor")
    advisor_email: str = os.getenv("ADVISOR_EMAIL", "admissions@executive-education.org")
    advisor_phone: str = os.getenv("ADVISOR_PHONE", "+1-555-0199")
    organization_name: str = os.getenv("ORGANIZATION_NAME", "Executive Education Consortium")
    portal_url: str = os.getenv("PORTAL_URL", "https://executive-education.org/admissions")
    assignment_email: str = os.getenv("ASSIGNMENT_EMAIL", "assignments@executive-education.org")


@dataclass
class Settings:
    # Service API keys with rotation support
    gemini_api_keys: List[str] = field(default_factory=lambda: [
        k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()
    ])
    deepgram_api_keys: List[str] = field(default_factory=lambda: [
        k.strip() for k in os.getenv("DEEPGRAM_API_KEYS", "").split(",") if k.strip()
    ])

    # Model preferences
    gemini_default_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_fallback_models: List[str] = field(default_factory=lambda: [
        "gemini-2.5-flash",
        "gemini-1.5-pro"
    ])

    # Mobile webhook / MacroDroid integration
    macrodroid_webhook_url: Optional[str] = os.getenv("MACRODROID_WEBHOOK_URL", None)
    macrodroid_device_id: Optional[str] = os.getenv("MACRODROID_DEVICE_ID", None)

    # Subsystem configs
    audio: AudioPipelineConfig = field(default_factory=AudioPipelineConfig)
    cdp_ports: CDPPortConfig = field(default_factory=CDPPortConfig)
    identity: IdentityConfig = field(default_factory=IdentityConfig)

    # File paths
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    logs_dir: Path = BASE_DIR / "logs"
    knowledge_base_dir: Path = BASE_DIR / "data" / "knowledge_base"
    database_file: Path = BASE_DIR / "data" / "leads_database.json"
    prompts_file: Path = BASE_DIR / "data" / "prompts.json"
    mock_leads_file: Path = BASE_DIR / "data" / "mock_leads.json"

    def __post_init__(self):
        # Guarantee runtime directories exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_base_dir.mkdir(parents=True, exist_ok=True)

    def validate_keys(self) -> Dict[str, bool]:
        """Validates that necessary operational keys are populated."""
        return {
            "gemini": len(self.gemini_api_keys) > 0,
            "deepgram": len(self.deepgram_api_keys) > 0,
            "macrodroid": bool(self.macrodroid_webhook_url or self.macrodroid_device_id)
        }


# Singleton configuration instance
settings = Settings()


def configure_logging(log_filename: str = "copilot.log", level: int = logging.INFO) -> logging.Logger:
    """Configures structured console and rotating file logging."""
    logger = logging.getLogger()
    logger.setLevel(level)

    # Avoid duplicate handlers if re-invoked
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        log_path = settings.logs_dir / log_filename
        file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        sys.stderr.write(f"Failed to initialize file logger: {e}\n")

    return logger
