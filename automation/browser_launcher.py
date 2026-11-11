import os
import time
import logging
import subprocess
import urllib.request
from typing import List, Dict, Any, Optional

from config.settings import settings

logger = logging.getLogger(__name__)


def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    """Probes the Chrome DevTools Protocol JSON version endpoint."""
    try:
        url = f"http://{host}:{port}/json/version"
        req = urllib.request.Request(url, headers={"User-Agent": "Copilot-CDP-Probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Polls CDP endpoint until process finishes initial handshake."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(port):
            return True
        time.sleep(0.4)
    return False


def find_browser_executable() -> Optional[str]:
    """Discovers installed Google Chrome or Microsoft Edge executable on Windows."""
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def launch_cdp_browser_instances() -> Dict[str, bool]:
    """Spawns isolated Chrome debug profiles with dedicated remote debugging ports.
    
    Port 9222: Salesforce Lightning CTI
    Port 9223: Dialer & Webmail
    Port 9224: AI Studio
    """
    browser_bin = find_browser_executable()
    if not browser_bin:
        logger.error("No compatible Chromium binary detected on host system.")
        return {}

    optimization_flags = [
        "--disable-features=AudioServiceSandbox,Translate,OptimizationHints",
        "--disable-site-isolation-trials",
        "--disable-extensions",
        "--disable-default-apps",
        "--renderer-process-limit=3",
        "--no-first-run"
    ]

    base_user_data = os.path.expandvars(r"%LOCALAPPDATA%\SalesCopilot\CDPProfiles")
    os.makedirs(base_user_data, exist_ok=True)

    profiles = [
        {
            "name": "salesforce",
            "port": settings.cdp_ports.salesforce,
            "data_dir": os.path.join(base_user_data, "SalesforceProfile"),
            "url": "https://login.salesforce.com/"
        },
        {
            "name": "dialer_and_mail",
            "port": settings.cdp_ports.dialer,
            "data_dir": os.path.join(base_user_data, "DialerProfile"),
            "url": "https://outlook.office.com/mail/"
        },
        {
            "name": "ai_studio",
            "port": settings.cdp_ports.ai_studio,
            "data_dir": os.path.join(base_user_data, "AIStudioProfile"),
            "url": "https://aistudio.google.com/prompts/new_chat"
        }
    ]

    results: Dict[str, bool] = {}

    for prof in profiles:
        port = prof["port"]
        name = prof["name"]

        if is_port_open(port):
            logger.info("CDP profile '%s' is already active on port %d.", name, port)
            results[name] = True
            continue

        cmd = [
            browser_bin,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={prof['data_dir']}",
            *optimization_flags,
            f"--app={prof['url']}"
        ]

        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("Launched CDP instance '%s' on port %d.", name, port)
            results[name] = wait_for_port(port, timeout=8.0)
        except Exception as e:
            logger.error("Failed launching browser instance '%s': %s", name, e)
            results[name] = False

    return results
