from __future__ import annotations

from dataclasses import dataclass

from scop.protocol.messages import SyslogMessage


@dataclass(frozen=True)
class ResolvedResult:
    ok: bool
    data: SyslogMessage  # must be a PAGE_END message (SCOP §11)
