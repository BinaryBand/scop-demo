from __future__ import annotations

from scop.adapters.config_adapter import ConfigAdapter
from scop.bases import BaseApp
from scop.models.config import AppConfig
from scop.models.protocol import MSGID, SyslogMessage
from scop.ports.config_port import ConfigPort
from scop.ports.streaming_result import StreamingResult
from scop.services.config_show_service import ConfigShowService
from scop.services.config_status_service import ConfigStatusService


def _form_params(config: AppConfig) -> list[dict]:
    """Build help-item params with current values as pre-populated defaults."""
    snap = config.snapshot
    return [
        {
            "name": "--store-dir",
            "kind": "flag",
            "metavar": "PATH",
            "default": snap.store_dir,
            "input_type": "path",
        },
        {
            "name": "--objects-dir",
            "kind": "flag",
            "metavar": "PATH",
            "default": snap.objects_dir,
            "input_type": "path",
        },
        {
            "name": "--skip-dirs",
            "kind": "flag",
            "metavar": "CSV",
            "default": ",".join(snap.skip_dirs),
            "input_type": "multi",
            "options": list(snap.skip_dirs)
            + [
                o
                for o in (
                    "__pycache__",
                    "node_modules",
                    "dist",
                    "build",
                    "target",
                    ".pytest_cache",
                    ".mypy_cache",
                    ".ruff_cache",
                    ".tox",
                    ".venv",
                    "venv",
                    ".eggs",
                    "coverage",
                    ".coverage",
                )
                if o not in snap.skip_dirs
            ],
        },
    ]


class ConfigApp(BaseApp):
    async def run(self, args: dict, stream: StreamingResult) -> None:
        room = "config"

        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.PAGE_BEGIN,
                room=room,
                msg="=== Config ===",
                data={
                    "title": "Config",
                    "subtitle": "Application configuration",
                    "icon": ":gear:",
                },
            )
        )

        port: ConfigPort = ConfigAdapter()

        # Collect update flags — any provided flag updates that key.
        updates: dict[str, str] = {}
        if args.get("store_dir"):
            updates["snapshot.store_dir"] = str(args["store_dir"])
        if args.get("objects_dir"):
            updates["snapshot.objects_dir"] = str(args["objects_dir"])
        if args.get("skip_dirs"):
            updates["snapshot.skip_dirs"] = str(args["skip_dirs"])

        if updates:
            for key, value in updates.items():
                try:
                    port.set_value(key, value)
                except ValueError as exc:
                    stream.emit(
                        SyslogMessage(
                            pri=4,
                            msgid=MSGID.SCALAR_SET,
                            room=room,
                            msg=str(exc),
                            data={
                                "id": "error",
                                "label": "error",
                                "value": str(exc),
                                "type": "string",
                            },
                        )
                    )
                    self._end(stream, room, ok=False)
                    return
            await ConfigStatusService(port=port, room=room).run(stream)
        elif args.get("help"):
            self._emit_help(stream, room, port)
        elif args.get("list"):
            await ConfigShowService(port=port, room=room).run(stream)
        else:
            await ConfigStatusService(port=port, room=room).run(stream)

        self._end(stream, room, ok=True)

    def _emit_help(self, stream: StreamingResult, room: str, port: ConfigPort) -> None:
        config = port.load()
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_DECLARE,
                room=room,
                msg="Configuration",
                data={"id": "help", "label": "Configuration", "ordered": False},
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_APPEND,
                room=room,
                msg="config",
                data={
                    "id": "help",
                    "item_id": "config",
                    "value": {
                        "command": "config",
                        "description": "Update configuration",
                        "kind": "action",
                        "params": _form_params(config),
                    },
                },
            )
        )
        stream.emit(
            SyslogMessage(
                pri=6,
                msgid=MSGID.LIST_END,
                room=room,
                msg="",
                data={"id": "help"},
            )
        )

    @staticmethod
    def _end(stream: StreamingResult, room: str, *, ok: bool) -> None:
        end = SyslogMessage(pri=6, msgid=MSGID.PAGE_END, room=room, msg="")
        stream.emit(end)
        stream.resolve(ok=ok, data=end)
