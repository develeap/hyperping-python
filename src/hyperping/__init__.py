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

from hyperping._version import __version__
from hyperping.client import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    HyperpingClient,
    RetryConfig,
)
from hyperping.endpoints import (
    API_BASE,
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
    IncidentType,
    IncidentUpdate,
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
    Outage,
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
    # Version
    "__version__",
    # Client
    "HyperpingClient",
    # Configuration
    "RetryConfig",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitState",
    # Endpoints — public types only (H5)
    "API_BASE",
    "Endpoint",
    "APIVersion",
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
    "IncidentType",
    "IncidentUpdate",
    "IncidentUpdateRequest",
    "IncidentUpdateType",
    "LocalizedText",
    # Deprecated aliases (accessible via __getattr__, removed in v0.3.0)
    "IncidentStatus",
    "IncidentUpdateCreate",
    # Maintenance
    "Maintenance",
    "MaintenanceCreate",
    "MaintenanceUpdate",
    "NotificationOption",
    # Reports
    "ReportPeriod",
    "OutageDetail",
    "OutageStats",
    # Outages
    "Outage",
    # Status Pages
    "StatusPage",
    "StatusPageCreate",
    "StatusPageUpdate",
    "StatusPageSubscriber",
]


def __getattr__(name: str) -> object:
    """Provide deprecated symbols with DeprecationWarning on access (H5, L3).

    ``HYPERPING_API_BASE`` and ``API_PATHS`` — legacy endpoint constants.
    ``IncidentStatus`` and ``IncidentUpdateCreate`` — legacy type aliases.

    All four will be removed in v0.3.0.
    """
    import warnings

    if name == "HYPERPING_API_BASE":
        warnings.warn(
            "HYPERPING_API_BASE is deprecated and will be removed in v0.3.0. "
            "Use API_BASE instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from hyperping.endpoints import API_BASE as _base

        return _base

    if name == "API_PATHS":
        warnings.warn(
            "API_PATHS is deprecated and will be removed in v0.3.0. "
            "Use the Endpoint enum instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        from hyperping.endpoints import API_PATHS as _paths

        return _paths

    if name == "IncidentStatus":
        warnings.warn(
            "IncidentStatus is deprecated and will be removed in v0.3.0. "
            "Use IncidentUpdateType instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return IncidentUpdateType

    if name == "IncidentUpdateCreate":
        warnings.warn(
            "IncidentUpdateCreate is deprecated and will be removed in v0.3.0. "
            "Use AddIncidentUpdateRequest instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return AddIncidentUpdateRequest

    # Expose endpoint helpers at package level (not in __all__ but still useful)
    if name in {"EndpointConfig", "ENDPOINTS", "get_endpoint_url", "get_version_for_endpoint"}:
        import hyperping.endpoints as _ep

        return getattr(_ep, name)

    raise AttributeError(f"module 'hyperping' has no attribute {name!r}")
