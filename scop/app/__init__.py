"""Wiring layer — constructs and injects concrete adapters into services via ports.

app/ assembles the dependency graph; it must not call service or adapter methods
directly (construction only). The public surface is AppDispatcher only.
"""

from scop.app.bases import BaseApp

__all__ = ["BaseApp"]
