"""Incident models for Hyperping API v3."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from hyperping.models._monitor_models import LocalizedText


class IncidentType(StrEnum):
    """Incident type values from v3 API."""

    OUTAGE = "outage"
    INCIDENT = "incident"


class IncidentUpdateType(StrEnum):
    """Incident update type values from v3 API."""

    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"
    UPDATE = "update"
    MONITORING = "monitoring"
    RESOLVED = "resolved"


class IncidentUpdate(BaseModel):
    """Model for an incident update from v3 API."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Update UUID")
    date: str = Field(..., description="Update timestamp ISO 8601")
    text: LocalizedText = Field(..., description="Localized update text")
    type: str = Field(..., description="Update type")


class AddIncidentUpdateRequest(BaseModel):
    """Model for adding an update to an incident.

    API: POST /v3/incidents/{uuid}/updates
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    text: LocalizedText = Field(..., description="Localized update text")
    type: IncidentUpdateType = Field(..., description="Update type")
    date: str = Field(..., description="Update date ISO 8601")


class IncidentCreate(BaseModel):
    """Model for creating a new incident via v3 API.

    API: POST /v3/incidents
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    title: LocalizedText = Field(..., description="Localized incident title")
    text: LocalizedText = Field(..., description="Localized incident message")
    type: IncidentType = Field(
        default=IncidentType.INCIDENT,
        description="Incident type: outage or incident",
    )
    affected_components: list[str] = Field(
        default_factory=list,
        alias="affectedComponents",
        description="Affected component UUIDs",
    )
    statuspages: list[str] = Field(
        ...,
        description="Status page UUIDs to display incident on (required)",
    )
    date: str | None = Field(
        default=None,
        description="Incident date ISO 8601 (optional)",
    )


class IncidentUpdateRequest(BaseModel):
    """Model for updating an existing incident via v3 API.

    API: PUT /v3/incidents/{uuid}
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    title: LocalizedText | None = None
    type: IncidentType | None = None
    affected_components: list[str] | None = Field(default=None, alias="affectedComponents")
    statuspages: list[str] | None = None


class Incident(BaseModel):
    """Model for an incident response from v3 API.

    API: GET /v3/incidents, GET /v3/incidents/{uuid}
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Incident UUID (inci_xxx)")
    date: str | None = Field(default=None, description="Incident date ISO 8601")
    title: LocalizedText = Field(..., description="Localized incident title")
    text: LocalizedText | None = Field(default=None, description="Localized incident message")
    type: str = Field(..., description="Incident type: outage or incident")
    affected_components: list[str] = Field(
        default_factory=list,
        alias="affectedComponents",
        description="Affected component UUIDs",
    )
    statuspages: list[str] = Field(
        default_factory=list,
        description="Status page UUIDs",
    )
    updates: list[IncidentUpdate] = Field(default_factory=list)

    @property
    def is_resolved(self) -> bool:
        """Check if incident has a resolved update."""
        return any(u.type == IncidentUpdateType.RESOLVED.value for u in self.updates)

    @property
    def title_en(self) -> str:
        """Get English title for convenience."""
        return self.title.en

    @property
    def text_en(self) -> str:
        """Get English text for convenience."""
        return self.text.en if self.text else ""
