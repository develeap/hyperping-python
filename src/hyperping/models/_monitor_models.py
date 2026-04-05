"""Monitor, report, and shared primitive models for Hyperping API."""

from __future__ import annotations

from enum import IntEnum, StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    def from_string(cls, text: str) -> LocalizedText:
        """Create LocalizedText from a simple string (English only)."""
        return cls(en=text)

    def get(self, lang: str, default: str = "") -> str:
        """Get text for a given language code, falling back to default."""
        value = getattr(self, lang, None)
        if value is None:
            # Try model_extra for languages beyond the explicit fields
            value = (self.model_extra or {}).get(lang)
        return value if value is not None else default


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
        """Get headers as a dictionary for convenience.

        Warning: The returned dict may contain sensitive values (e.g.,
        Authorization tokens) that the user configured on this monitor.
        Avoid logging the result without redacting sensitive keys first.
        """
        return {h.name: h.value for h in self.request_headers}

    @staticmethod
    def _remap_legacy_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Remap legacy field names to current API field names.

        Returns a new dict; the input is never mutated.
        """
        remapped = {**data}
        if "frequency" in remapped and "check_frequency" not in remapped:
            remapped["check_frequency"] = remapped.pop("frequency")
        if "method" in remapped and "http_method" not in remapped:
            remapped["http_method"] = remapped.pop("method")
        if "body" in remapped and "request_body" not in remapped:
            remapped["request_body"] = remapped.pop("body")
        if "headers" in remapped and "request_headers" not in remapped:
            headers = remapped.pop("headers")
            if isinstance(headers, dict):
                remapped["request_headers"] = [
                    {"name": k, "value": v} for k, v in headers.items()
                ]
            else:
                remapped["request_headers"] = headers
        if "expected_status" in remapped and "expected_status_code" not in remapped:
            remapped["expected_status_code"] = str(remapped.pop("expected_status"))
        return remapped


class MonitorCreate(MonitorBase):
    """Model for creating a new monitor.

    All fields from MonitorBase are available. Required: name, url, protocol.
    """

    @model_validator(mode="before")
    @classmethod
    def remap_and_validate_create(cls, data: Any) -> Any:
        """Remap legacy field names before validation and check DNS field usage."""
        if isinstance(data, dict):
            return MonitorBase._remap_legacy_fields(data)
        return data

    @model_validator(mode="after")
    def validate_dns_fields(self) -> MonitorCreate:
        """Raise if DNS-specific fields are set on a non-DNS monitor."""
        dns_fields = {
            "dns_record_type": self.dns_record_type,
            "dns_nameserver": self.dns_nameserver,
            "dns_expected_answer": self.dns_expected_answer,
        }
        set_dns_fields = [k for k, v in dns_fields.items() if v is not None]
        protocol = self.protocol
        if set_dns_fields and str(protocol) != MonitorProtocol.DNS.value:
            raise ValueError(
                f"DNS fields {set_dns_fields} are only valid when protocol='dns'"
            )
        return self


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

    @model_validator(mode="before")
    @classmethod
    def normalize_monitor_response(cls, data: Any) -> Any:
        """Normalize API response quirks before field validation."""
        if not isinstance(data, dict):
            return data

        # Build a clean copy to avoid mutating the input
        remapped = {**data}

        # Handle both uuid and monitorUuid (legacy alias)
        if "monitorUuid" in remapped and "uuid" not in remapped:
            remapped["uuid"] = remapped.pop("monitorUuid")

        # Apply shared legacy field remapping
        remapped = MonitorBase._remap_legacy_fields(remapped)

        # Handle API returning headers as dict sometimes
        if "request_headers" in remapped and isinstance(remapped["request_headers"], dict):
            remapped["request_headers"] = [
                {"name": k, "value": v}
                for k, v in remapped["request_headers"].items()
            ]

        # Handle API returning null for optional fields
        if remapped.get("request_headers") is None:
            remapped["request_headers"] = []
        if remapped.get("http_method") is None:
            remapped.pop("http_method", None)  # Use MonitorBase default (GET)
        if "expected_status_code" in remapped:
            if remapped["expected_status_code"] is None:
                remapped.pop("expected_status_code")  # Use MonitorBase default ("2xx")
            elif isinstance(remapped["expected_status_code"], int):
                remapped["expected_status_code"] = str(remapped["expected_status_code"])

        return remapped


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
    """Model for API error responses.

    Note: Not currently returned by any client method. Retained for consumers
    who parse error JSON manually. Consider private if unused by callers.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    error: str = Field(default="Unknown error")
    message: str | None = None
    details: list[dict[str, Any]] | None = None
