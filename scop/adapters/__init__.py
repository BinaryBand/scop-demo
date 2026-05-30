"""Driven adapters — every class here must subclass Adapter and declare
`port: ClassVar[type[Port]]` matching the port of the same filename.

Adapters may import from scop.utils and scop.models.
Adapters must NOT import from scop.services or scop.app.
"""

from scop.models.bases import Adapter

__all__ = ["Adapter"]
