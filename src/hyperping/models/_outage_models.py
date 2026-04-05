"""Outage models for Hyperping API v2 (C5: typed Outage model)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Outage(BaseModel):
    """Model for an auto-detected outage from the Hyperping v2 API.

    API: GET /v2/outages

    Uses ``extra="ignore"`` and ``frozen=True`` to tolerate undocumented fields
    and ensure immutability.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Outage UUID")
    monitor_uuid: str | None = Field(
        default=None,
        alias="monitorUuid",
        description="UUID of the affected monitor",
    )
    started_at: str | None = Field(
        default=None,
        alias="startedAt",
        description="Outage start time ISO 8601",
    )
    ended_at: str | None = Field(
        default=None,
        alias="endedAt",
        description="Outage end time ISO 8601 (None if still ongoing)",
    )
    acknowledged: bool = Field(
        default=False,
        description="Whether the outage has been acknowledged",
    )
    resolved: bool = Field(
        default=False,
        description="Whether the outage has been resolved",
    )
    cause: str | None = Field(
        default=None,
        description="Human-readable outage cause",
    )

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Outage:
        """Parse an outage from a raw API response dict."""
        return cls.model_validate(data)
