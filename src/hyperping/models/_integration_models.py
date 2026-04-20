"""Integration models: notification channel configuration."""

from pydantic import BaseModel, ConfigDict, Field


class Integration(BaseModel):
    """Configured notification integration (Slack, Teams, PagerDuty, etc.)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Integration UUID")
    name: str = Field(..., description="Integration display name")
    integration_type: str = Field(..., alias="type", description="Channel type")
    active: bool = Field(default=True, description="Whether the integration is active")
