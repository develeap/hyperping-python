"""Healthcheck models for Hyperping API v2.

Healthchecks are push-based cron/heartbeat monitors. The API endpoint is
``/v2/healthchecks``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthcheckBase(BaseModel):
    """Base model for healthcheck data.

    Field names match the official Hyperping API (snake_case).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Healthcheck display name")
    period: int = Field(..., description="Expected ping interval in seconds")
    grace: int = Field(..., description="Grace period in seconds before alerting")
    escalation_policy: str | None = Field(
        default=None,
        description="Escalation policy UUID",
    )
    project_uuid: str | None = Field(
        default=None,
        description="Project UUID this healthcheck belongs to",
    )


class HealthcheckCreate(HealthcheckBase):
    """Model for creating a new healthcheck.

    All fields from HealthcheckBase are required on create.
    """


class HealthcheckUpdate(BaseModel):
    """Model for updating an existing healthcheck (all fields optional)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    period: int | None = None
    grace: int | None = None
    escalation_policy: str | None = None


class Healthcheck(HealthcheckBase):
    """Model for a healthcheck response from the Hyperping API.

    API: GET /v2/healthchecks, GET /v2/healthchecks/{uuid}

    Uses ``extra="allow"`` so new API fields are preserved instead of silently
    dropped, and ``frozen=True`` for immutability (D-06: is_paused not paused).
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Healthcheck unique identifier")
    is_paused: bool = Field(default=False, description="Whether the healthcheck is paused")
    is_down: bool = Field(default=False, description="Whether the healthcheck is currently down")
    last_pinged_at: datetime | None = Field(
        default=None,
        description="Timestamp of the last received ping (ISO 8601)",
    )

    @classmethod
    def from_raw(cls, data: dict[str, Any]) -> Healthcheck:
        """Parse a healthcheck from a raw API response dict."""
        return cls.model_validate(data)
