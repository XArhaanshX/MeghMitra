"""Persistence shapes for a trigger evaluation.

The engine's *decision* lives in `trigger_engine`; these models are what gets
stored after that decision. Extra fields the HTTP layer needs (the matched
rule, the citation) stay on the route response — they are not duplicated here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TriggerEvent(BaseModel):
    """One evaluation of moisture + forecast against the approved rule base.

    Written even when the outcome is ABSTAIN — an audit log that only records
    the times we spoke would hide the more common, and more important, silence.
    `block_id` on the SQL table is a UUID FK to `blocks` and stays null until a
    block registry exists; `block_key` is the string the moisture state used.
    """

    id: UUID = Field(default_factory=uuid4)
    block_key: str
    rule_id: UUID | None = None
    detected_at: datetime
    condition: str | None = None
    reasons: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class Advisory(BaseModel):
    """A non-silent emission: an action plus the rule it retrieved.

    ABSTAIN does not produce a row here. The matching `TriggerEvent` is the
    record of the evaluation; this row is the record of something having been
    said.
    """

    id: UUID = Field(default_factory=uuid4)
    trigger_event_id: UUID
    rule_id: UUID | None = None
    generated_at: datetime
    action: str
    reason: str | None = None
    channel: str = "api"
    delivered_to: str | None = None
