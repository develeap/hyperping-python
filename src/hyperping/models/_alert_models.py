"""Alert models for streaming helpers (PY-10).

This module is provisional. The Alert model fields are derived from the monitors
list endpoint. When Hyperping ships a discrete alerts endpoint, the model will
be reconciled with the real API shape.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AlertType(StrEnum):
    """Alert transition type."""

    DOWN = "down"
    UP = "up"
    DEGRADED = "degraded"


class Alert(BaseModel):
    """A monitor state-transition event yielded by stream_alerts.

    Provisional model: fields are inferred from the monitors list endpoint.
    When Hyperping ships a dedicated alerts endpoint, this model will be
    reconciled against the real API shape.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    monitor_uuid: str = Field(..., alias="monitorUuid")
    monitor_name: str = Field(..., alias="monitorName")
    type: AlertType = Field(...)
    timestamp: str = Field(...)
