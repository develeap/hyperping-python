"""Observability models: anomalies and probe logs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MonitorAnomaly(BaseModel):
    """Anomaly detected on a monitor."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    id: int = Field(..., description="Anomaly ID")
    timestamp: str = Field(..., description="Detection time ISO 8601")
    end_timestamp: str | None = Field(
        default=None, alias="endTimestamp", description="End time ISO 8601"
    )
    type: str = Field(..., description="Anomaly type (error_rate, latency, etc.)")
    region: str | None = Field(default=None, description="Affected regions")
    value: float = Field(default=0, description="Measured value")
    baseline: float = Field(default=0, description="Expected baseline value")
    score: float = Field(default=0, description="Anomaly score (0-1)")
    consecutive_count: int = Field(default=0, alias="consecutiveCount")
    resolved: int = Field(default=0, description="1 if resolved, 0 if ongoing")
    outage_uuid: str | None = Field(
        default=None, alias="outageUuid", description="Linked outage UUID"
    )


class ProbeLog(BaseModel):
    """HTTP probe log entry."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    id: str = Field(default="", description="Log entry ID")
    status_code: int = Field(default=0, alias="statusCode", description="HTTP status code")
    elapsed_time: int = Field(default=0, alias="elapsedTime", description="Response time in ms")
    location: str = Field(default="", description="Probe region")
    date: str = Field(default="", description="Timestamp ISO 8601")
    is_error: int = Field(default=0, alias="isError", description="1 if error, 0 if success")
    continent: str = Field(default="", description="Continent code")
    bytes: int = Field(default=0, description="Response body size")
    headers: str = Field(default="", description="Response headers")


class ProbeLogResponse(BaseModel):
    """Wrapper for probe log list responses."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    pings: list[ProbeLog] = Field(default_factory=list, description="Probe log entries")
    anomalies: list[dict[str, Any]] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)
