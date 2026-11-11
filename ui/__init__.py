"""Workstation graphical user interface and event orchestration."""

from .workstation import SalesCopilotWorkstationApp
from .components import build_workstation_ui
from .events import process_gui_events

__all__ = ["SalesCopilotWorkstationApp", "build_workstation_ui", "process_gui_events"]
