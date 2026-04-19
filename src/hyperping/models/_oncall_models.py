"""On-call models: schedules and escalation policies."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OnCallSchedule(BaseModel):
    """On-call rotation schedule."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Schedule UUID")
    name: str = Field(..., description="Schedule name")
    current_on_call: str | None = Field(
        default=None, alias="currentOnCall", description="Current on-call person"
    )


class EscalationPolicy(BaseModel):
    """Escalation policy with step chain."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Policy UUID")
    name: str = Field(..., description="Policy name")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Escalation steps")
