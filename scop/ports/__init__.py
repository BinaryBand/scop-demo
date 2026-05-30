"""Port interfaces — every class here must subclass Port.

Ports are called by services and implemented by adapters.
Type references to models use TYPE_CHECKING imports only.
"""
from scop.models.bases import Port

__all__ = ["Port"]
