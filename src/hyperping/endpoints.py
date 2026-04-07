"""API endpoint definitions - single source of truth for all Hyperping API paths.

This module uses frozen dataclasses and StrEnum for type-safe, immutable endpoint
configuration following modern Python best practices.

Usage:
    from hyperping.endpoints import API_BASE, Endpoint

    # Type-safe endpoint access with IDE autocompletion
    url = f"{API_BASE}{Endpoint.MONITORS}"           # https://api.hyperping.io/v1/monitors
    url = f"{API_BASE}{Endpoint.INCIDENTS}"          # https://api.hyperping.io/v3/incidents
    url = f"{API_BASE}{Endpoint.MONITORS}/mon_123"   # https://api.hyperping.io/v1/monitors/mon_123

    # Access metadata
    Endpoint.MONITORS.version      # "v1"
    Endpoint.MONITORS.resource     # "monitors"
    Endpoint.INCIDENTS.version     # "v3"
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# =============================================================================
# API Base URL - Single Source of Truth
# =============================================================================

API_BASE: Final[str] = "https://api.hyperping.io"
"""Base URL for all Hyperping API requests. Never includes trailing slash."""


# =============================================================================
# API Versions
# =============================================================================


class APIVersion(StrEnum):
    """API versions used by Hyperping.

    Different resources use different API versions. This enum documents
    the available versions and provides type safety.
    """

    V1 = "v1"
    """Version 1 - Used by monitors and maintenance endpoints."""

    V2 = "v2"
    """Version 2 - Used by reporting endpoints."""

    V3 = "v3"
    """Version 3 - Used by incidents endpoints."""


# =============================================================================
# Endpoint Configuration
# =============================================================================


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """Immutable configuration for an API endpoint.

    Attributes:
        version: API version (e.g., "v1", "v2", "v3")
        resource: Resource name/path (e.g., "monitors", "incidents")
        description: Human-readable description for documentation

    Example:
        >>> config = EndpointConfig(version=APIVersion.V1, resource="monitors")
        >>> str(config)
        '/v1/monitors'
    """

    version: APIVersion
    resource: str
    description: str = ""

    def __str__(self) -> str:
        """Return the full path for this endpoint."""
        return f"/{self.version}/{self.resource}"

    @property
    def path(self) -> str:
        """Alias for string representation."""
        return str(self)


# =============================================================================
# Endpoint Registry - Type-Safe Endpoint Access
# =============================================================================


class Endpoint(StrEnum):
    """Type-safe endpoint paths for the Hyperping API.

    This enum provides:
    - IDE autocompletion for endpoint names
    - Type safety (typos cause AttributeError, not silent bugs)
    - Immutability (endpoints cannot be modified at runtime)
    - Self-documenting code

    Usage:
        # Direct string usage (StrEnum inherits from str)
        url = f"{API_BASE}{Endpoint.MONITORS}"
        url = f"{API_BASE}{Endpoint.MONITORS}/{monitor_id}"

        # Access version info via ENDPOINTS dict
        version = ENDPOINTS[Endpoint.MONITORS].version
    """

    # Monitors - v1
    MONITORS = "/v1/monitors"
    """Monitor CRUD operations. Version: v1"""

    # Maintenance - v1
    MAINTENANCE = "/v1/maintenance-windows"
    """Maintenance window operations. Version: v1"""

    # Incidents - v3
    INCIDENTS = "/v3/incidents"
    """Incident management operations. Version: v3"""

    # Reports - v2
    REPORTS = "/v2/reporting/monitor-reports"
    """Uptime and performance reporting. Version: v2"""

    # Outages - v2
    OUTAGES = "/v2/outages"
    """Auto-detected outage management. Version: v2"""

    # Status Pages - v2
    STATUSPAGES = "/v2/statuspages"
    """Status page management. Version: v2"""

    # Healthchecks - v2
    HEALTHCHECKS = "/v2/healthchecks"
    """Healthcheck (cron/heartbeat monitor) management. Version: v2"""


# Detailed endpoint metadata for programmatic access
ENDPOINTS: Final[dict[Endpoint, EndpointConfig]] = {
    Endpoint.MONITORS: EndpointConfig(
        version=APIVersion.V1,
        resource="monitors",
        description="Monitor CRUD operations - create, read, update, delete monitors",
    ),
    Endpoint.MAINTENANCE: EndpointConfig(
        version=APIVersion.V1,
        resource="maintenance-windows",
        description="Maintenance window scheduling and management",
    ),
    Endpoint.INCIDENTS: EndpointConfig(
        version=APIVersion.V3,
        resource="incidents",
        description="Incident creation, updates, and resolution",
    ),
    Endpoint.REPORTS: EndpointConfig(
        version=APIVersion.V2,
        resource="reporting/monitor-reports",
        description="Uptime percentages and performance metrics",
    ),
    Endpoint.OUTAGES: EndpointConfig(
        version=APIVersion.V2,
        resource="outages",
        description="Auto-detected outage management (list, ack, resolve, escalate)",
    ),
    Endpoint.STATUSPAGES: EndpointConfig(
        version=APIVersion.V2,
        resource="statuspages",
        description="Status page CRUD, subscribers management",
    ),
    Endpoint.HEALTHCHECKS: EndpointConfig(
        version=APIVersion.V2,
        resource="healthchecks",
        description="Healthcheck (cron/heartbeat) CRUD and pause/resume",
    ),
}


# =============================================================================
# Backward Compatibility - Deprecation Layer
# =============================================================================

# These maintain backward compatibility with existing code.
# TODO: Deprecate in future version and migrate all usage to Endpoint enum.

HYPERPING_API_BASE: Final[str] = API_BASE
"""Deprecated: Use API_BASE instead."""

API_PATHS: Final[dict[str, str]] = {
    "monitors": Endpoint.MONITORS.value,
    "maintenance": Endpoint.MAINTENANCE.value,
    "incidents": Endpoint.INCIDENTS.value,
    "reports": Endpoint.REPORTS.value,
    "outages": Endpoint.OUTAGES.value,
    "statuspages": Endpoint.STATUSPAGES.value,
    "healthchecks": Endpoint.HEALTHCHECKS.value,
}
"""Deprecated: Use Endpoint enum instead for type safety."""


# =============================================================================
# Utility Functions
# =============================================================================


def get_endpoint_url(endpoint: Endpoint, resource_id: str | None = None) -> str:
    """Build a full URL for an API endpoint.

    Args:
        endpoint: The API endpoint
        resource_id: Optional resource ID for single-resource operations

    Returns:
        Full URL string

    Example:
        >>> get_endpoint_url(Endpoint.MONITORS)
        'https://api.hyperping.io/v1/monitors'
        >>> get_endpoint_url(Endpoint.MONITORS, "mon_123")
        'https://api.hyperping.io/v1/monitors/mon_123'
    """
    if resource_id:
        return f"{API_BASE}{endpoint}/{resource_id}"
    return f"{API_BASE}{endpoint}"


def get_version_for_endpoint(endpoint: Endpoint) -> APIVersion:
    """Get the API version used by an endpoint.

    Args:
        endpoint: The API endpoint

    Returns:
        The API version enum value

    Example:
        >>> get_version_for_endpoint(Endpoint.INCIDENTS)
        <APIVersion.V3: 'v3'>
    """
    return ENDPOINTS[endpoint].version
