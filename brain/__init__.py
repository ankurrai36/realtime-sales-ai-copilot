"""Contextual RAG engine, prompt orchestrator, and database integration."""

from .database import (
    load_database,
    save_database,
    create_or_get_lead,
    update_lead_history,
    get_lead_history,
    update_lead_summaries,
    get_lead_summaries
)
from .knowledge_loader import load_program_knowledge, load_prompts
from .rag_engine import SalesAIBrain, DualChatService

__all__ = [
    "load_database",
    "save_database",
    "create_or_get_lead",
    "update_lead_history",
    "get_lead_history",
    "update_lead_summaries",
    "get_lead_summaries",
    "load_program_knowledge",
    "load_prompts",
    "SalesAIBrain",
    "DualChatService"
]
