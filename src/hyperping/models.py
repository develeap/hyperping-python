"""Pydantic models for Hyperping API requests and responses."""

from datetime import UTC, datetime
from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HttpMethod(StrEnum):
    """HTTP methods supported by Hyperping monitors."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"


class MonitorFrequency(IntEnum):
    """Monitor check frequencies in seconds."""

    SECONDS_10 = 10
    SECONDS_20 = 20
    SECONDS_30 = 30
    MINUTES_1 = 60
    MINUTES_2 = 120
    MINUTES_3 = 180
    MINUTES_5 = 300
    MINUTES_10 = 600
    MINUTES_30 = 1800
    HOURS_1 = 3600
    HOURS_6 = 21600
    HOURS_12 = 43200
    HOURS_24 = 86400


class MonitorTimeout(IntEnum):
    """Monitor request timeout options in seconds."""

    SECONDS_5 = 5
    SECONDS_10 = 10
    SECONDS_15 = 15
    SECONDS_20 = 20


class Region(StrEnum):
    """Hyperping monitoring regions.

    Combined from official Hyperping API documentation and real API responses.
    """

    # Europe
    PARIS = "paris"
    FRANKFURT = "frankfurt"
    AMSTERDAM = "amsterdam"
    LONDON = "london"

    # Asia Pacific
    SINGAPORE = "singapore"
    SYDNEY = "sydney"
    TOKYO = "tokyo"
    SEOUL = "seoul"
    MUMBAI = "mumbai"
    BANGALORE = "bangalore"

    # Americas
    VIRGINIA = "virginia"
    CALIFORNIA = "california"
    SAN_FRANCISCO = "sanfrancisco"
    OREGON = "oregon"
    NYC = "nyc"
    TORONTO = "toronto"
    SAO_PAULO = "saopaulo"

    # Middle East / Africa
    BAHRAIN = "bahrain"
    CAPE_TOWN = "capetown"


# Default regions (common subset for balanced global coverage)
DEFAULT_REGIONS = [
    Region.PARIS,
    Region.FRANKFURT,
    Region.AMSTERDAM,
    Region.LONDON,
    Region.SINGAPORE,
    Region.SYDNEY,
    Region.TOKYO,
    Region.VIRGINIA,
]


class MonitorProtocol(StrEnum):
    """Monitor protocol types."""

    HTTP = "http"
    PORT = "port"
    ICMP = "icmp"
    DNS = "dns"


class DnsRecordType(StrEnum):
    """DNS record types supported by Hyperping DNS monitors."""

    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    MX = "MX"
    NS = "NS"
    TXT = "TXT"
    SOA = "SOA"
    SRV = "SRV"
    CAA = "CAA"
    PTR = "PTR"


class RequestHeader(BaseModel):
    """HTTP header for monitor requests.

    API format: [{"name": "Header-Name", "value": "header-value"}]
    """

    name: str = Field(..., description="Header name")
    value: str = Field(..., description="Header value")


class LocalizedText(BaseModel):
    """Localized text supporting multiple languages.

    Used for incident/maintenance titles and descriptions.
    API format: {"en": "English text", "fr": "French text"}
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    en: str = Field(..., description="English text (required)")
    fr: str | None = Field(default=None, description="French text")
    de: str | None = Field(default=None, description="German text")
    es: str | None = Field(default=None, description="Spanish text")

    @classmethod
    def from_string(cls, text: str) -> "LocalizedText":
        """Create LocalizedText from a simple string (English only)."""
        return cls(en=text)


class MonitorBase(BaseModel):
    """Base model for monitor data.

    Field names match the official Hyperping API (snake_case).
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="Monitor display name")
    url: str = Field(..., description="URL to monitor")
    protocol: MonitorProtocol = Field(
        default=MonitorProtocol.HTTP,
        description="Monitor protocol: http, port, or icmp",
    )
    http_method: HttpMethod = Field(
        default=HttpMethod.GET,
        alias="http_method",
        description="HTTP method",
    )
    check_frequency: int = Field(
        default=30,
        alias="check_frequency",
        description="Check frequency in seconds",
    )
    regions: list[str] = Field(
        default_factory=lambda: [r.value for r in DEFAULT_REGIONS],
        description="Monitoring regions",
    )
    request_headers: list[RequestHeader] = Field(
        default_factory=list,
        alias="request_headers",
        description="Custom HTTP headers [{name, value}]",
    )
    request_body: str | None = Field(
        default=None,
        alias="request_body",
        description="Request body for POST/PUT/PATCH",
    )
    follow_redirects: bool = Field(
        default=True,
        alias="follow_redirects",
        description="Follow HTTP redirects",
    )
    expected_status_code: str = Field(
        default="2xx",
        alias="expected_status_code",
        description="Expected status code (e.g., '200' or '2xx')",
    )
    required_keyword: str | None = Field(
        default=None,
        alias="required_keyword",
        description="Required keyword in response body",
    )
    paused: bool = Field(default=False, description="Whether monitor is paused")
    port: int | None = Field(default=None, description="Port number (for port protocol)")
    alerts_wait: int | None = Field(
        default=None,
        alias="alerts_wait",
        description="Seconds to wait before alerting",
    )
    escalation_policy: str | None = Field(
        default=None,
        alias="escalation_policy",
        description="Escalation policy UUID",
    )

    # DNS-specific fields (only used when protocol="dns")
    dns_record_type: str | None = Field(
        default=None,
        alias="dns_record_type",
        description="DNS record type (A, AAAA, CNAME, MX, etc.)",
    )
    dns_nameserver: str | None = Field(
        default=None,
        alias="dns_nameserver",
        description="Custom nameserver to query (e.g. 8.8.8.8)",
    )
    dns_expected_answer: str | None = Field(
        default=None,
        alias="dns_expected_answer",
        description="Expected DNS answer to match against",
    )

    @field_validator("escalation_policy", mode="before")
    @classmethod
    def coerce_escalation_policy(cls, v: object) -> str | None:
        """Accept both plain UUID strings and {uuid, name} dicts from the API."""
        if isinstance(v, dict):
            return v.get("uuid")
        return v  # type: ignore[return-value]

    # Helper methods for backward compatibility
    def get_headers_dict(self) -> dict[str, str]:
        """Get headers as a dictionary for convenience."""
        return {h.name: h.value for h in self.request_headers}

    @staticmethod
    def _remap_legacy_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Remap legacy field names to current API field names."""
        if "frequency" in data and "check_frequency" not in data:
            data["check_frequency"] = data.pop("frequency")
        if "method" in data and "http_method" not in data:
            data["http_method"] = data.pop("method")
        if "body" in data and "request_body" not in data:
            data["request_body"] = data.pop("body")
        if "headers" in data and "request_headers" not in data:
            headers = data.pop("headers")
            if isinstance(headers, dict):
                data["request_headers"] = [{"name": k, "value": v} for k, v in headers.items()]
            else:
                data["request_headers"] = headers
        if "expected_status" in data and "expected_status_code" not in data:
            data["expected_status_code"] = str(data.pop("expected_status"))
        return data


class MonitorCreate(MonitorBase):
    """Model for creating a new monitor.

    All fields from MonitorBase are available. Required: name, url, protocol.
    """

    def __init__(self, **data: Any) -> None:
        MonitorBase._remap_legacy_fields(data)
        super().__init__(**data)


class MonitorUpdate(BaseModel):
    """Model for updating an existing monitor (all fields optional)."""

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = None
    protocol: MonitorProtocol | None = None
    http_method: HttpMethod | None = Field(default=None, alias="http_method")
    check_frequency: int | None = Field(default=None, alias="check_frequency")
    regions: list[str] | None = None
    request_headers: list[RequestHeader] | None = Field(default=None, alias="request_headers")
    request_body: str | None = Field(default=None, alias="request_body")
    follow_redirects: bool | None = Field(default=None, alias="follow_redirects")
    expected_status_code: str | None = Field(default=None, alias="expected_status_code")
    required_keyword: str | None = Field(default=None, alias="required_keyword")
    paused: bool | None = None
    port: int | None = None
    alerts_wait: int | None = Field(default=None, alias="alerts_wait")
    escalation_policy: str | None = Field(default=None, alias="escalation_policy")
    dns_record_type: str | None = Field(default=None, alias="dns_record_type")
    dns_nameserver: str | None = Field(default=None, alias="dns_nameserver")
    dns_expected_answer: str | None = Field(default=None, alias="dns_expected_answer")


class Monitor(MonitorBase):
    """Model for a monitor response from Hyperping API."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Monitor unique identifier (mon_xxx)")
    project_uuid: str | None = Field(default=None, alias="projectUuid")

    # Override paused from MonitorBase (it's in response, not just create)
    paused: bool = Field(default=False, description="Whether monitor is paused")
    down: bool = Field(default=False, description="Whether monitor is currently down")

    def __init__(self, **data: Any) -> None:
        # Handle both uuid and monitorUuid (legacy alias)
        if "monitorUuid" in data and "uuid" not in data:
            data["uuid"] = data.pop("monitorUuid")

        # Apply shared legacy field remapping
        MonitorBase._remap_legacy_fields(data)

        # Handle API returning headers as dict sometimes
        if "request_headers" in data and isinstance(data["request_headers"], dict):
            data["request_headers"] = [
                {"name": k, "value": v} for k, v in data["request_headers"].items()
            ]

        # Handle API returning null for optional fields
        if "request_headers" in data and data["request_headers"] is None:
            data["request_headers"] = []
        if "http_method" in data and data["http_method"] is None:
            del data["http_method"]  # Use MonitorBase default (GET)
        if "expected_status_code" in data:
            if data["expected_status_code"] is None:
                del data["expected_status_code"]  # Use MonitorBase default ("2xx")
            elif isinstance(data["expected_status_code"], int):
                data["expected_status_code"] = str(data["expected_status_code"])

        super().__init__(**data)


class ReportPeriod(BaseModel):
    """Time period for a monitor report."""

    from_date: str = Field(..., alias="from", description="Start date ISO 8601")
    to_date: str = Field(..., alias="to", description="End date ISO 8601")

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class OutageDetail(BaseModel):
    """Details about a specific outage."""

    start_date: str = Field(..., alias="startDate")
    end_date: str = Field(..., alias="endDate")

    model_config = ConfigDict(populate_by_name=True, frozen=True, extra="ignore")


class OutageStats(BaseModel):
    """Statistics about outages in a report period."""

    count: int = Field(default=0, description="Total number of outages")
    total_downtime: int = Field(
        default=0, alias="totalDowntime", description="Total downtime in seconds"
    )
    total_downtime_formatted: str = Field(
        default="", alias="totalDowntimeFormatted", description="Human-readable downtime"
    )
    longest_outage: int = Field(
        default=0, alias="longestOutage", description="Longest outage in seconds"
    )
    longest_outage_formatted: str = Field(
        default="", alias="longestOutageFormatted", description="Human-readable longest outage"
    )
    details: list[OutageDetail] = Field(default_factory=list, description="Outage details")

    model_config = ConfigDict(populate_by_name=True, frozen=True)


class MonitorReport(BaseModel):
    """Model for monitor uptime report from v2 API.

    API: GET /v2/reporting/monitor-reports?period=30d
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Monitor UUID")
    name: str = Field(..., description="Monitor name")
    protocol: str = Field(..., description="Monitor protocol")
    period: ReportPeriod = Field(..., description="Report time period")
    sla: float = Field(..., description="SLA percentage (e.g., 99.184)")
    outages: OutageStats = Field(..., description="Outage statistics")
    mttr: int = Field(default=0, description="Mean time to recovery in seconds")
    mttr_formatted: str = Field(
        default="0s", alias="mttrFormatted", description="MTTR human-readable"
    )


class MonitorListResponse(BaseModel):
    """Response model for list monitors endpoint."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    monitors: list[Monitor] = Field(default_factory=list)
    total: int = Field(default=0)


class APIErrorResponse(BaseModel):
    """Model for API error responses."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    error: str = Field(default="Unknown error")
    message: str | None = None
    details: list[dict[str, Any]] | None = None


# ==================== Incident Models ====================


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


# Legacy aliases for backward compatibility (used by _incidents_mixin.py)
IncidentStatus = IncidentUpdateType  # Old name -> new name
IncidentUpdateCreate = AddIncidentUpdateRequest  # Old name -> new name


# ==================== Maintenance Models ====================


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

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

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
            from datetime import datetime as dt

            try:
                start = dt.fromisoformat(self.start_date.replace("Z", "+00:00"))
                end = dt.fromisoformat(self.end_date.replace("Z", "+00:00"))
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


# ==================== Status Page Models ====================


class StatusPage(BaseModel):
    """Model for a status page response from v2 API.

    API: GET /v2/statuspages, GET /v2/statuspages/{uuid}
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Status page UUID")
    name: str = Field(..., description="Status page display name")
    subdomain: str = Field(..., description="Status page subdomain")
    custom_domain: str | None = Field(
        default=None, alias="customDomain", description="Custom domain"
    )
    public: bool = Field(default=True, description="Whether the page is publicly accessible")
    monitors: list[str] = Field(
        default_factory=list, description="Monitor UUIDs shown on this page"
    )


class StatusPageCreate(BaseModel):
    """Model for creating a new status page.

    API: POST /v2/statuspages
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="Status page display name")
    subdomain: str = Field(..., description="Status page subdomain")
    custom_domain: str | None = Field(
        default=None, alias="customDomain", description="Custom domain"
    )
    public: bool = Field(default=True, description="Whether the page is publicly accessible")
    monitors: list[str] = Field(
        default_factory=list, description="Monitor UUIDs shown on this page"
    )


class StatusPageUpdate(BaseModel):
    """Model for updating an existing status page (all fields optional).

    API: PUT /v2/statuspages/{uuid}
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    subdomain: str | None = None
    custom_domain: str | None = Field(default=None, alias="customDomain")
    public: bool | None = None
    monitors: list[str] | None = None


class StatusPageSubscriber(BaseModel):
    """Model for a status page subscriber.

    API: GET /v2/statuspages/{uuid}/subscribers
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True, frozen=True)

    id: str = Field(..., description="Subscriber ID")
    email: str = Field(..., description="Subscriber email address")
