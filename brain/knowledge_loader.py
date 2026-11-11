import os
import json
import glob
import logging
from pathlib import Path
from typing import Dict, Any

from config.settings import settings

logger = logging.getLogger(__name__)


def load_program_knowledge() -> Dict[str, Any]:
    """Dynamically aggregates all JSON curriculum and playbook files from the knowledge base."""
    master_knowledge: Dict[str, Any] = {}
    kb_dir = settings.knowledge_base_dir

    if not kb_dir.exists():
        logger.warning("Knowledge base directory does not exist: %s", kb_dir)
        return master_knowledge

    json_files = list(kb_dir.glob("*.json"))
    if not json_files:
        logger.info("No JSON knowledge base files detected in: %s", kb_dir)
        return master_knowledge

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    master_knowledge.update(data)
        except Exception as e:
            logger.error("Failed loading knowledge base file '%s': %s", file_path.name, e)

    logger.info("Successfully loaded %d curriculum specifications from %d files.", len(master_knowledge), len(json_files))
    return master_knowledge


def load_prompts() -> Dict[str, Any]:
    """Loads standardized sales playbooks and persona rules."""
    prompts_path = settings.prompts_file
    if prompts_path.exists():
        try:
            with open(prompts_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Error reading prompts catalog: %s", e)
    return {}
