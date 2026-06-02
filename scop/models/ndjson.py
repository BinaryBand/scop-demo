"""Pydantic models for SCOP NDJSON event lines.

This module defines a strict, non-coercing model for a single NDJSON event
line following the SCOP `event_base` rules. Extra keys are forbidden and
basic semantic validations are enforced (single-line `msg`, non-negative
`pri`, etc.).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

TYPE = Literal["number", "string", "boolean", "duration", "bytes"]
INTENT = Literal["query", "action"]
PARAM_KIND = Literal["flag", "positional"]
HELP_KIND = Literal["action", "group"]

# Conservative ISO 8601 duration matcher for SCOP `duration` scalar values.
# Accepts examples like: P1D, PT2H, PT1M30S, P1DT2H, P2W.
ISO8601_DURATION_RE = re.compile(
    r"^P(?=.+)(?:\d+Y)?(?:\d+M)?(?:\d+W)?(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+(?:\.\d+)?S)?)?$"
)

Text = Annotated[str, StringConstraints(strict=True)]
SingleLineText = Annotated[
    str,
    StringConstraints(strict=True, pattern=r"^[^\r\n]*$"),
]
GemojiCode = Annotated[
    str,
    # SCOP requires :name: token shape for gemoji codes.
    StringConstraints(strict=True, pattern=r"^:[A-Za-z0-9_+\-]+:$"),
]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
Flag = Annotated[bool, Field(strict=True)]
Pri = Annotated[int, Field(strict=True, ge=0, le=7)]

OptText = Text | None
OptGemojiCode = GemojiCode | None
OptNonNegativeInt = NonNegativeInt | None
OptFlag = Flag | None

JSONMap = dict[Text, Any]
TextList = list[Text]

MSGID = Literal[
    "PAGE_BEGIN",
    "PAGE_END",
    "PROCESS_BEGIN",
    "PROCESS_UPDATE",
    "PROCESS_END",
    "PROCESS_LOG",
    "SCALAR_SET",
    "SCALAR_CLEAR",
    "LIST_DECLARE",
    "LIST_APPEND",
    "LIST_UPDATE",
    "LIST_REMOVE",
    "LIST_END",
    "TABLE_DECLARE",
    "TABLE_ROW",
    "TABLE_UPDATE",
    "TABLE_END",
]

# Canonical validation map using spec-compliant JSON keys
MSGID_MAP: dict[MSGID, tuple[set[str], set[str]]] = {
    "PAGE_BEGIN": ({"title"}, {"subtitle", "icon", "intent"}),
    "PAGE_END": (set(), set()),
    "PROCESS_BEGIN": (
        {"id", "label"},
        {"total", "dry_run", "recursive"},
    ),
    "PROCESS_UPDATE": (
        {"id", "current"},
        {"total", "label"},
    ),
    "PROCESS_END": (
        {"id", "ok"},
        {"dry_run"},
    ),
    "PROCESS_LOG": (
        {"id"},
        set(),
    ),
    "SCALAR_SET": ({"id", "label", "value", "type"}, {"unit", "display_hint"}),
    "SCALAR_CLEAR": ({"id"}, set()),
    "LIST_DECLARE": ({"id", "label", "ordered"}, set()),
    "LIST_APPEND": ({"id", "item_id", "value"}, set()),
    "LIST_UPDATE": ({"id", "item_id", "value"}, set()),
    "LIST_REMOVE": ({"id", "item_id"}, set()),
    "LIST_END": ({"id"}, set()),
    "TABLE_DECLARE": ({"id", "label", "schema"}, {"display_hint"}),
    "TABLE_ROW": ({"id", "row_id", "values"}, set()),
    "TABLE_UPDATE": ({"id", "row_id", "values"}, set()),
    "TABLE_END": ({"id"}, set()),
}

HELP_LIST_MSGIDS = ("LIST_APPEND", "LIST_UPDATE")

DISPLAY_HINT_ALLOWED_BY_MSGID: dict[str, set[str]] = {
    "SCALAR_SET": {"badge"},
    "TABLE_DECLARE": {"table", "chart", "cards"},
}
DISPLAY_HINT_ERROR_BY_MSGID: dict[str, str] = {
    "SCALAR_SET": "Producers MUST NOT use display_hint values not defined in this spec ('badge')",
    "TABLE_DECLARE": "display_hint for TABLE_DECLARE must be 'table', 'chart', or 'cards'",
}


class HelpParam(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: Text
    kind: PARAM_KIND
    type: OptText = None
    required: OptFlag = None
    short: OptText = None
    metavar: OptText = None
    repeatable: OptFlag = None
    description: OptText = None


class HelpItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command: Text
    description: Text
    kind: HELP_KIND | None = None
    params: list[HelpParam] | None = None


class NDJSONEvent(BaseModel):
    """Strict model for a single SCOP NDJSON event.

    Fields mirror `event_base` in `static/NORTH_STAR.yaml` and enforce full compliance
    with the SCOP v0.1.2-draft specification.
    """

    # strict=True prevents implicit type coercions (e.g., bool -> int or int -> str)
    # populate_by_name=True allows programmatic instantiation using 'table_schema'
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
    )

    # Core Required Fields (§4.2 & §5)
    pri: Pri = Field(..., description="RFC 5424 PRI — facility*8 + severity")
    msgid: MSGID = Field(..., description="SCOP message identifier")
    room: OptText = Field(..., description="Derived room path or null")
    msg: SingleLineText = Field(..., description="Human-readable single-line message")

    # Optional Infrastructure Fields (§4.2)
    ts: datetime | None = Field(None, description="ISO 8601 timestamp")
    app: OptText = Field(None, description="Application name")
    pid: OptNonNegativeInt = Field(None, description="Process id")

    # Dynamic Vocabulary Fields (§7)
    title: OptText = Field(None, description="PAGE_BEGIN title")
    subtitle: OptText = Field(None, description="PAGE_BEGIN subtitle")
    icon: OptGemojiCode = Field(None, description="PAGE_BEGIN icon gemoji code")
    intent: INTENT = Field(
        "query", description="PAGE_BEGIN view integration strategy (default: 'query')"
    )

    id: OptText = Field(None, description="Identifier for dynamic structural items")
    label: OptText = Field(None, description="Human readable label")
    total: OptNonNegativeInt = Field(None, description="Total expected steps or size")
    current: OptNonNegativeInt = Field(None, description="Current progress step")
    ok: OptFlag = Field(None, description="Process termination success status")
    dry_run: OptFlag = Field(None, description="Flag indicating mock action execution")
    recursive: OptFlag = Field(None, description="Flag indicating recursive modifier context")
    force: OptFlag = Field(None, description="Flag indicating forced modifier context")

    type: TYPE | None = Field(None, description="Abstract scalar value type")
    value: Any | None = Field(None, description="Scalar or structural entry value representation")
    unit: OptText = Field(None, description="Display unit denomination")
    display_hint: OptText = Field(None, description="Advisory presentation suggestion")

    item_id: OptText = Field(None, description="Unique list element identifier")
    ordered: OptFlag = Field(None, description="List item sorting configuration indication")

    # Renamed to avoid protected namespace conflicts while targeting the correct JSON key
    table_schema: TextList | None = Field(
        None, alias="schema", description="Ordered collection of table schema keys"
    )
    row_id: OptText = Field(None, description="Unique table row entity key")
    values: JSONMap | None = Field(
        None,
        description="Relational data dictionary mapping schema keys to cell values",
    )

    _TEXT_DUPLICATE_FIELDS: ClassVar[tuple[str, ...]] = (
        "id",
        "label",
        "title",
        "subtitle",
        "item_id",
        "row_id",
        "app",
    )
    _MSGID_VALIDATORS: ClassVar[tuple[str, ...]] = (
        "_validate_scalar_set_value_matrix",
        "_validate_display_hint_rules",
        "_validate_help_item_structure",
    )

    @field_validator("pri", mode="before")
    @classmethod
    def _validate_pri(cls, v: object) -> int:
        if isinstance(v, bool):
            raise TypeError("pri must be an integer, not a boolean")
        if not isinstance(v, int):
            raise TypeError("pri must be an integer")
        return v

    @model_validator(mode="after")
    def _validate_spec_conformance(self) -> NDJSONEvent:
        # 1. Isolate vocabulary fields while converting Python attribute names to JSON aliases
        provided_vocabulary_fields = self._provided_vocabulary_fields()

        core_fields = {"pri", "msgid", "room", "msg", "ts", "app", "pid"}
        provided_vocabulary_fields -= core_fields

        # 2. Map precise structural boundaries (Required, Optional) fields per MSGID family (§7)
        required_fields, optional_fields = MSGID_MAP[self.msgid]
        allowed_fields = required_fields | optional_fields

        # Enforce non-empty fallback rules universally except for PAGE_END (§7.1)
        if self.msgid != "PAGE_END" and self.msg.strip() == "":
            raise ValueError("msg must not be empty")

        # Catch missing keys per dynamic configuration
        missing = required_fields - provided_vocabulary_fields
        if missing:
            raise ValueError(f"Missing required fields for {self.msgid}: {sorted(missing)}")

        # Catch keys that shouldn't exist for this specific family
        forbidden = provided_vocabulary_fields - allowed_fields
        if forbidden:
            raise ValueError(f"Fields {sorted(forbidden)} are forbidden for msgid='{self.msgid}'")

        # 3. Contextual Field Verification Rules
        for check_name in self._MSGID_VALIDATORS:
            getattr(self, check_name)()

        # 5. Prohibit verbatim duplication of msg against any other scalar text field
        for fname in self._TEXT_DUPLICATE_FIELDS:
            val = getattr(self, fname, None)
            if isinstance(val, str) and val == self.msg:
                raise ValueError(f"msg must not verbatim duplicate field '{fname}'")

        # Additionally check help-item inner fields when present
        if (
            self.msgid in ("LIST_APPEND", "LIST_UPDATE")
            and self.id == "help"
            and isinstance(self.value, dict)
        ):
            cmd = self.value.get("command")
            desc = self.value.get("description")
            if isinstance(cmd, str) and cmd == self.msg:
                raise ValueError("msg must not verbatim duplicate help-item 'command'")
            if isinstance(desc, str) and desc == self.msg:
                raise ValueError("msg must not verbatim duplicate help-item 'description'")

        return self

    def _provided_vocabulary_fields(self) -> set[str]:
        # model_fields is a class-level attribute; access it from the class to avoid
        # Pydantic deprecation warnings about instance-level access.
        cls_fields = type(self).model_fields
        return {
            (cls_fields[field_name].alias or field_name)
            for field_name in self.model_fields_set
            if getattr(self, field_name) is not None
        }

    def _validate_scalar_set_value_matrix(self) -> None:
        if self.msgid != "SCALAR_SET":
            return

        t, v = self.type, self.value
        if t == "bytes":
            if isinstance(v, bool) or not isinstance(v, int) or v < 0:
                raise TypeError(
                    "For type='bytes', value MUST be a non-negative JSON integer "
                    "absolute byte count"
                )
        elif t == "duration":
            if not isinstance(v, str):
                raise TypeError("For type='duration', value MUST be an ISO 8601 duration string")
            if not ISO8601_DURATION_RE.fullmatch(v):
                raise ValueError(
                    "For type='duration', value MUST be a valid ISO 8601 duration string "
                    "(e.g. 'PT1M30S')"
                )
        elif t == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise TypeError("For type='number', value MUST be an integer or float")
        elif t == "string":
            if not isinstance(v, str):
                raise TypeError("For type='string', value MUST be a string")
        elif t == "boolean" and not isinstance(v, bool):
            raise TypeError("For type='boolean', value MUST be a boolean")

    def _validate_display_hint_rules(self) -> None:
        if self.display_hint is None:
            return

        allowed = DISPLAY_HINT_ALLOWED_BY_MSGID.get(self.msgid)
        if allowed is None:
            return
        if self.display_hint not in allowed:
            raise ValueError(DISPLAY_HINT_ERROR_BY_MSGID[self.msgid])

    def _validate_help_item_structure(self) -> None:
        if self.msgid not in HELP_LIST_MSGIDS or self.id != "help":
            return

        if not isinstance(self.value, dict):
            raise TypeError("Help item value must be a structural JSON dictionary object")

        item = HelpItem.model_validate(self.value)

        if not item.params:
            return

        current_stage = 0  # 0: positional, 1: required flag, 2: optional flag
        last_name = ""

        for param in item.params:
            if param.kind != "flag" and param.short is not None:
                raise ValueError("Param 'short' is valid for kind='flag' only")

            # Calculate implied or explicit parameter requirements
            p_req = param.required if param.required is not None else param.kind == "positional"

            if param.kind == "positional":
                stage = 0
            elif param.kind == "flag" and p_req:
                stage = 1
            else:
                stage = 2

            # Strict validation of order matrix rules (§8.1)
            if stage < current_stage:
                raise ValueError(
                    "Params ordering violation: positionals MUST precede flags; "
                    "required flags MUST precede optional flags."
                )
            if stage == current_stage and param.name < last_name:
                raise ValueError(
                    f"Params sorting violation: within each group, parameters must be "
                    f"alphabetical by name. Overlap found: '{param.name}' after '{last_name}'."
                )

            current_stage = stage
            last_name = param.name
