"""Maintenance window models for Hyperping API v1."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hyperping.models._monitor_models import LocalizedText


class NotificationOption(StrEnum):
    """Maintenance notification options."""

    SCHEDULED = "scheduled"
    IMMEDIATE = "immediate"


class MaintenanceCreate(BaseModel):
    """Model for creating a maintenance window via v1 API.

    API: POST /v1/maintenance-windows
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="Internal name")
    start_date: str = Field(
        ...,
        alias="start_date",
        description="Start date ISO 8601 (e.g., 2025-05-18T14:30:00Z)",
    )
    end_date: str = Field(
        ...,
        alias="end_date",
        description="End date ISO 8601 (e.g., 2025-05-18T15:30:00Z)",
    )
    monitors: list[str] = Field(
        ...,
        description="Array of monitor UUIDs affected by maintenance",
    )
    statuspages: list[str] = Field(
        default_factory=list,
        description="Array of status page UUIDs to display maintenance on",
    )
    title: LocalizedText | None = Field(
        default=None,
        description="Localized public title",
    )
    text: LocalizedText | None = Field(
        default=None,
        description="Localized public description",
    )
    notification_option: NotificationOption | None = Field(
        default=None,
        alias="notificationOption",
        description="When to notify: scheduled or immediate",
    )
    notification_minutes: int | None = Field(
        default=None,
        alias="notificationMinutes",
        description="Minutes before start to send notification",
    )


class MaintenanceUpdate(BaseModel):
    """Model for updating a maintenance window via v1 API.

    API: PUT /v1/maintenance-windows/{uuid}
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_date: str | None = Field(default=None, alias="start_date")
    end_date: str | None = Field(default=None, alias="end_date")
    monitors: list[str] | None = None


class Maintenance(BaseModel):
    """Model for a maintenance window response from v1 API.

    API: GET /v1/maintenance-windows, GET /v1/maintenance-windows/{uuid}
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Maintenance UUID (mw_xxx)")
    name: str = Field(..., description="Internal name")
    title: LocalizedText | None = Field(default=None, description="Localized public title")
    text: LocalizedText | None = Field(default=None, description="Localized public description")

    @field_validator("title", "text", mode="before")
    @classmethod
    def coerce_empty_localized_text(cls, v: object) -> object:
        """Convert empty dicts {} to None — the API returns {} for unset titles."""
        if isinstance(v, dict) and not v:
            return None
        return v

    start_date: str | None = Field(default=None, alias="start_date")
    end_date: str | None = Field(default=None, alias="end_date")
    timezone: str = Field(default="UTC", description="Timezone")
    monitors: list[str] = Field(default_factory=list, description="Affected monitor UUIDs")
    statuspages: list[str] = Field(default_factory=list, description="Status page UUIDs")
    bulk_uuid: str | None = Field(default=None, alias="bulkUuid")
    created_by: str | None = Field(default=None, alias="createdBy")
    created_at: str | None = Field(default=None, alias="createdAt")
    notification_option: str | None = Field(default=None, alias="notificationOption")
    notification_minutes: int | None = Field(default=None, alias="notificationMinutes")

    def is_active(self, at_time: datetime | None = None) -> bool:
        """Check if maintenance is currently active.

        Args:
            at_time: Time to check (defaults to now)

        Returns:
            True if maintenance window is currently active
        """
        if at_time is None:
            at_time = datetime.now(UTC)

        if self.start_date and self.end_date:
            try:
                start = datetime.fromisoformat(self.start_date.replace("Z", "+00:00"))
                end = datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
                # Make at_time timezone-aware if needed
                if at_time.tzinfo is None:
                    at_time = at_time.replace(tzinfo=UTC)
                return start <= at_time <= end
            except (ValueError, AttributeError):
                return False

        return False

    def affects_monitor(self, monitor_uuid: str) -> bool:
        """Check if this maintenance affects a specific monitor.

        Args:
            monitor_uuid: Monitor UUID to check

        Returns:
            True if monitor is affected by this maintenance
        """
        return monitor_uuid in self.monitors

    @property
    def title_en(self) -> str | None:
        """Get English title for convenience."""
        return self.title.en if self.title else None

    @property
    def text_en(self) -> str | None:
        """Get English text for convenience."""
        return self.text.en if self.text else None
