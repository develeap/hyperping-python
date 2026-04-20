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

    Uses ``extra="allow"`` so new API fields are preserved instead of silently
    dropped, and ``frozen=True`` for immutability.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

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

    Uses ``extra="allow"`` so new API fields are preserved instead of silently
    dropped, and ``frozen=True`` for immutability.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

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
    """Single event in an outage lifecycle timeline."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    type: str = Field(..., description="Event type (anomaly_detected, outage_detected, etc.)")
    timestamp: str = Field(..., description="Event time ISO 8601")
    data: dict[str, Any] = Field(default_factory=dict, description="Event-specific payload")


class OutageMonitorSummary(BaseModel):
    """Monitor summary embedded in outage timeline responses."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Monitor UUID")
    name: str = Field(default="", description="Monitor name")
    url: str = Field(default="", description="Monitor URL")
    protocol: str = Field(default="", description="Monitor protocol")


class OutageTimeline(BaseModel):
    """Full outage timeline from get_outage_timeline."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    outage: Outage = Field(..., description="Outage details")
    monitor: OutageMonitorSummary = Field(..., description="Monitor details")
    escalation_policy: dict[str, Any] | None = Field(
        default=None, alias="escalationPolicy", description="Linked escalation policy"
    )
    timeline: list[OutageTimelineEvent] = Field(
        default_factory=list, description="Chronological event list"
    )
