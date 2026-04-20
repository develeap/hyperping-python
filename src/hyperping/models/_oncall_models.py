"""On-call models: schedules and escalation policies."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OnCallSchedule(BaseModel):
    """On-call rotation schedule."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Schedule UUID")
    name: str = Field(..., description="Schedule name")
    current_on_call: str | None = Field(
        default=None, alias="currentOnCall", description="Current on-call person"
    )


class EscalationPolicy(BaseModel):
    """Escalation policy with step chain."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Policy UUID")
    name: str = Field(..., description="Policy name")
    steps: list[dict[str, Any]] = Field(default_factory=list, description="Escalation steps")


class TeamMember(BaseModel):
    """Team member from list_team_members."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="User UUID")
    email: str = Field(default="", description="Email address")
    name: str = Field(default="", description="Display name")
    phone: str | None = Field(default=None, description="Phone number")
    profile_picture_url: str | None = Field(
        default=None, alias="profilePictureUrl", description="Profile picture URL"
    )
    account_role: str = Field(default="", alias="accountRole", description="Role in project")
