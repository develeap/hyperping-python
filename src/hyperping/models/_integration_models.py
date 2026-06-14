"""Integration models: notification channel configuration."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Integration(BaseModel):
    """Configured notification integration (Slack, Teams, PagerDuty, etc.)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Integration UUID")
    name: str = Field(..., description="Integration display name")
    integration_type: str = Field(
        ..., alias="channel", description="Channel type (e.g. 'teams', 'slack')"
    )
    created_by: str | None = Field(
        default=None,
        alias="createdBy",
        description="Creator UUID (list endpoint) or email address (get endpoint)",
    )
    created_at: str | None = Field(
        default=None, alias="createdAt", description="ISO-8601 creation timestamp"
    )
    region: str | None = Field(default=None, description="Deployment region, if set")
    metadata: Any | None = Field(default=None, description="Arbitrary integration metadata")
