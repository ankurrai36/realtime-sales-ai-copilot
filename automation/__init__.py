"""Browser automation, DOM scraping, and multi-channel outreach engine."""

from .browser_launcher import launch_cdp_browser_instances, is_port_open
from .salesforce_client import SalesforceClient
from .contaque_client import ContaqueClient
from .scrapers import scrape_salesforce_lead, scrape_dialer_lead
from .outreach import OutreachDispatcher
from .sheet_campaign import SheetCampaignManager
from .crm_orchestrator import CRMOrchestrator, SalesforceBot

__all__ = [
    "launch_cdp_browser_instances",
    "is_port_open",
    "SalesforceClient",
    "ContaqueClient",
    "scrape_salesforce_lead",
    "scrape_dialer_lead",
    "OutreachDispatcher",
    "SheetCampaignManager",
    "CRMOrchestrator",
    "SalesforceBot"
]
