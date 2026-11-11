"""Real-Time Conversational AI Copilot & CRM Orchestrator

Master bootloader and execution entry point.
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config.settings import settings, configure_logging


def elevate_process_priority():
    """Sets HIGH_PRIORITY_CLASS on Windows to ensure sub-millisecond audio callback scheduling."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(),
                0x00000080  # HIGH_PRIORITY_CLASS
            )
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Real-Time Conversational AI Copilot & CRM Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validates environment settings and API key readiness without launching GUI"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level"
    )

    args = parser.parse_args()

    # Configure structured logging
    numeric_level = getattr(logging, args.log_level.upper(), logging.INFO)
    logger = configure_logging(level=numeric_level)

    logger.info("Starting Real-Time Conversational AI Copilot & CRM Orchestrator...")

    validation = settings.validate_keys()
    logger.info(
        "Environment verification: Gemini Keys: %s | Deepgram Keys: %s | Webhooks: %s",
        "Configured" if validation["gemini"] else "Missing (Check .env)",
        "Configured" if validation["deepgram"] else "Missing (Check .env)",
        "Configured" if validation["macrodroid"] else "Optional/Not Set"
    )

    if args.validate_config:
        print("\n=== Configuration Summary ===")
        print(f"Project Directory : {settings.base_dir}")
        print(f"Data Directory    : {settings.data_dir}")
        print(f"Gemini API Keys   : {len(settings.gemini_api_keys)} loaded")
        print(f"Deepgram API Keys : {len(settings.deepgram_api_keys)} loaded")
        print(f"CDP Ports         : CRM={settings.cdp_ports.salesforce}, Dialer={settings.cdp_ports.dialer}, AI={settings.cdp_ports.ai_studio}")
        print(f"Advisor Identity  : {settings.identity.advisor_name} ({settings.identity.organization_name})")
        print("Validation finished successfully.")
        return 0

    elevate_process_priority()

    # Launch GUI Workstation
    from ui.workstation import SalesCopilotWorkstationApp
    app = SalesCopilotWorkstationApp()
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
