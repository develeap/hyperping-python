"""On-call models: schedules and escalation policies."""

from pydantic import BaseModel, ConfigDict, Field


class OnCallSchedule(BaseModel):
    """On-call rotation schedule."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Schedule UUID")
    name: str = Field(..., description="Schedule name")
    current_on_call: str | None = Field(
        default=None, alias="currentOnCall", description="Current on-call person"
    )


class EscalationStep(BaseModel):
    """Single step in an escalation policy."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Step UUID")
    wait_before: int = Field(
        default=0, description="Minutes to wait before escalating to this step"
    )
    channels: list[str] = Field(default_factory=list, description="Integration UUIDs to notify")
    temp_id: str | None = Field(
        default=None, alias="tempId", description="Temporary client-side ID"
    )


class EscalationPolicy(BaseModel):
    """Escalation policy with step chain."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Policy UUID")
    name: str = Field(..., description="Policy name")
    steps: list[EscalationStep] = Field(default_factory=list, description="Escalation steps")
    created_by: str | None = Field(
        default=None, alias="createdBy", description="Creator UUID or email"
    )
    created_at: str | None = Field(
        default=None, alias="createdAt", description="ISO-8601 creation timestamp"
    )
    grouped_alerts_window: int | None = Field(
        default=None, description="Alert grouping window in seconds"
    )
    grouped_alerts_enabled: int | None = Field(
        default=None, description="Whether alert grouping is enabled (0/1)"
    )
    monitor_count: int | None = Field(
        default=None, alias="monitorCount", description="Number of monitors using this policy"
    )


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
    sso_picture_url: str | None = Field(
        default=None, alias="ssoPictureUrl", description="SSO provider profile picture URL"
    )
    account_role: str = Field(default="", alias="accountRole", description="Role in project")
