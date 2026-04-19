"""Reporting models: status summary and aggregated metrics."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StatusSummary(BaseModel):
    """Aggregate status summary from a single API call."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    total_monitors: int = Field(default=0, alias="totalMonitors")
    up_count: int = Field(default=0, alias="upCount")
    down_count: int = Field(default=0, alias="downCount")
    paused_count: int = Field(default=0, alias="pausedCount")
    down_monitors: list[dict[str, Any]] = Field(default_factory=list, alias="downMonitors")
