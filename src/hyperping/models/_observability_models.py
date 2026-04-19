"""Observability models: anomalies, probe logs, and alert notifications."""

from pydantic import BaseModel, ConfigDict, Field


class MonitorAnomaly(BaseModel):
    """Anomaly detected on a monitor (flapping, latency spike, etc.)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    anomaly_type: str = Field(..., alias="anomalyType", description="Anomaly category")
    started_at: str | None = Field(
        default=None, alias="startedAt", description="Start time ISO 8601"
    )
    ended_at: str | None = Field(default=None, alias="endedAt", description="End time ISO 8601")
    severity: str = Field(default="info", description="Anomaly severity")


class ProbeLog(BaseModel):
    """HTTP probe log entry from a monitor check."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    status: int | None = Field(default=None, description="HTTP status code")
    location: str | None = Field(default=None, description="Probe region")
    response_time_ms: float | None = Field(
        default=None, alias="responseTimeMs", description="Response time in ms"
    )
    level: str | None = Field(default=None, description="Log level")
    timestamp: str | None = Field(default=None, description="Timestamp ISO 8601")


class AlertNotification(BaseModel):
    """Alert notification record from notification history."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Alert UUID")
    monitor_uuid: str | None = Field(
        default=None, alias="monitorUuid", description="Affected monitor UUID"
    )
    channel: str = Field(default="unknown", description="Notification channel")
    sent_at: str | None = Field(default=None, alias="sentAt", description="Send time ISO 8601")
    resolved_at: str | None = Field(
        default=None, alias="resolvedAt", description="Resolution time ISO 8601"
    )
