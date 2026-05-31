"""Domain logic — every class here must subclass Service.

Services call out through Port interfaces only; never construct adapters directly.
Imports from scop.adapters are forbidden.
"""

from scop.framework.bases import Service

__all__ = ["Service"]
