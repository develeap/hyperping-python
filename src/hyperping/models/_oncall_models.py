"""On-call models: schedules and escalation policies."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OnCallSchedule(BaseModel):
    """On-call rotation schedule.

    .. note::
        This model has not been validated against a real API response. Neither
        the production nor the test account had any on-call schedules configured
        as of 2026-06-13 (re-probed via MCP). The declared fields are inferred
        from the MCP tool description. Additional fields (rotation config,
        linked escalation policies) may exist in the actual response and will
        land in ``model_extra`` due to ``extra="allow"``. Re-run the MCP probe
        after creating at least one schedule and reconcile this model against
        the real response shape (ticket #333911).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Schedule UUID (format: \"sch_...\")")
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
