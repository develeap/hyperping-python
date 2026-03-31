"""Hyperping API client.

A Python client for the `Hyperping <https://hyperping.io>`_ monitoring API,
providing typed models, automatic retries with exponential backoff, and a
circuit breaker for fault tolerance.

Quick start::

    from hyperping import HyperpingClient

    with HyperpingClient(api_key="sk_...") as client:
        monitors = client.list_monitors()
        for m in monitors:
            print(f"{m.name}: {'down' if m.down else 'up'}")
"""

__version__ = "0.1.0"

from hyperping.client import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    HyperpingClient,
    RetryConfig,
)
from hyperping.endpoints import (
    API_BASE,
    API_PATHS,
    ENDPOINTS,
    HYPERPING_API_BASE,
    APIVersion,
    Endpoint,
    EndpointConfig,
    get_endpoint_url,
    get_version_for_endpoint,
)
from hyperping.exceptions import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)
from hyperping.models import (
    DEFAULT_REGIONS,
    AddIncidentUpdateRequest,
    APIErrorResponse,
    DnsRecordType,
    HttpMethod,
    Incident,
    IncidentCreate,
    IncidentStatus,
    IncidentType,
    IncidentUpdate,
    IncidentUpdateCreate,
    IncidentUpdateRequest,
    IncidentUpdateType,
    LocalizedText,
    Maintenance,
    MaintenanceCreate,
    MaintenanceUpdate,
    Monitor,
    MonitorBase,
    MonitorCreate,
    MonitorFrequency,
    MonitorListResponse,
    MonitorProtocol,
    MonitorReport,
    MonitorTimeout,
    MonitorUpdate,
    NotificationOption,
    OutageDetail,
    OutageStats,
    Region,
    ReportPeriod,
    RequestHeader,
    StatusPage,
    StatusPageCreate,
    StatusPageSubscriber,
    StatusPageUpdate,
)

__all__ = [
    # Client
    "HyperpingClient",
    # Configuration
    "RetryConfig",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitState",
    # Endpoints
    "API_BASE",
    "Endpoint",
    "APIVersion",
    "EndpointConfig",
    "ENDPOINTS",
    "get_endpoint_url",
    "get_version_for_endpoint",
    # Backward compatibility
    "HYPERPING_API_BASE",
    "API_PATHS",
    # Exceptions
    "HyperpingAPIError",
    "HyperpingAuthError",
    "HyperpingNotFoundError",
    "HyperpingRateLimitError",
    "HyperpingValidationError",
    # Monitor enums
    "HttpMethod",
    "MonitorFrequency",
    "MonitorTimeout",
    "Region",
    "MonitorProtocol",
    "DnsRecordType",
    "DEFAULT_REGIONS",
    # Monitors
    "MonitorBase",
    "Monitor",
    "MonitorCreate",
    "MonitorUpdate",
    "MonitorReport",
    "MonitorListResponse",
    "RequestHeader",
    # Incidents
    "AddIncidentUpdateRequest",
    "Incident",
    "IncidentCreate",
    "IncidentStatus",
    "IncidentType",
    "IncidentUpdate",
    "IncidentUpdateCreate",
    "IncidentUpdateRequest",
    "IncidentUpdateType",
    "LocalizedText",
    # Maintenance
    "Maintenance",
    "MaintenanceCreate",
    "MaintenanceUpdate",
    "NotificationOption",
    # Reports
    "ReportPeriod",
    "OutageDetail",
    "OutageStats",
    "APIErrorResponse",
    # Status Pages
    "StatusPage",
    "StatusPageCreate",
    "StatusPageUpdate",
    "StatusPageSubscriber",
]
