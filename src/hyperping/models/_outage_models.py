"""Outage models for Hyperping API v2 (C5: typed Outage model)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OutageAction(BaseModel):
    """Model for the response returned by outage action endpoints.

    Covers acknowledge, resolve, and escalate operations:
      - POST /v2/outages/{uuid}/acknowledge
      - POST /v2/outages/{uuid}/resolve
      - POST /v2/outages/{uuid}/escalate

    Uses ``extra="ignore"`` to tolerate additional fields the API may return
    and ``frozen=True`` for immutability.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    status: str = Field(
        ..., description='Action result, e.g. "acknowledged", "resolved", "escalated"'
    )
    message: str | None = Field(
        default=None, description="Optional message included with the action"
    )

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> OutageAction:
        """Parse an outage action response from a raw API response dict."""
        return cls.model_validate(data)


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


class OutageTimelineEvent(BaseModel):
    """Single event in an outage lifecycle timeline.

    Events include detection, cross-region verification, alert dispatch,
    acknowledgement, and resolution.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    event_type: str = Field(..., alias="eventType", description="Event category")
    timestamp: str = Field(..., description="Event time ISO 8601")
    detail: str | None = Field(default=None, description="Event detail text")


class OutageTimeline(BaseModel):
    """Full lifecycle timeline for an outage."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    outage_uuid: str = Field(..., alias="outageUuid", description="Outage UUID")
    events: list[OutageTimelineEvent] = Field(
        default_factory=list, description="Chronological list of events"
    )
