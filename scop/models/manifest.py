from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, TypeAdapter
from pydantic.dataclasses import dataclass

ManifestValueType = Literal[
    "string",
    "number",
    "boolean",
    "path",
    "datetime",
    "duration",
    "bytes",
    "choice",
]


@dataclass(frozen=True)
class ManifestParam:
    __pydantic_config__ = ConfigDict(extra="forbid")

    name: str
    kind: Literal["flag", "positional"]
    type: ManifestValueType
    short: str | None = None
    metavar: str | None = None
    description: str | None = None
    required: bool | None = None
    repeatable: bool | None = None
    default: Any | None = None
    pattern: str | None = None
    choices: list[str] | None = None
    min: float | None = None
    max: float | None = None
    format: str | None = None
    min_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class ManifestCommand:
    __pydantic_config__ = ConfigDict(extra="forbid")

    name: str
    exec: str
    description: str
    kind: Literal["action", "group"]
    navigates: str | None = None
    param: list[ManifestParam] = Field(default_factory=list)


@dataclass(frozen=True)
class ManifestRoomStat:
    __pydantic_config__ = ConfigDict(extra="forbid")

    id: str
    label: str
    type: ManifestValueType
    unit: str | None = None


@dataclass(frozen=True)
class ManifestRoomList:
    __pydantic_config__ = ConfigDict(extra="forbid", populate_by_name=True)

    schema_: list[str] = Field(alias="schema")
    display_hint: Literal["table", "chart", "cards"] | None = None


@dataclass(frozen=True)
class ManifestRoom:
    __pydantic_config__ = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    title: str
    subtitle: str | None = None
    icon: str | None = None
    stat: list[ManifestRoomStat] = Field(default_factory=list)
    list_: ManifestRoomList | None = Field(default=None, alias="list")
    command: list[ManifestCommand] = Field(default_factory=list)


@dataclass(frozen=True)
class ManifestApp:
    __pydantic_config__ = ConfigDict(extra="forbid")

    name: str
    version: str
    scop_version: str
    description: str | None = None
    global_param: list[ManifestParam] = Field(default_factory=list)


@dataclass(frozen=True)
class ScopManifest:
    __pydantic_config__ = ConfigDict(extra="forbid")

    app: ManifestApp
    room: list[ManifestRoom] = Field(default_factory=list)

    @classmethod
    def model_validate(cls, payload: object) -> ScopManifest:
        return TypeAdapter(cls).validate_python(payload)

    @classmethod
    def model_json_schema(cls) -> dict[str, Any]:
        return TypeAdapter(cls).json_schema(by_alias=True)
