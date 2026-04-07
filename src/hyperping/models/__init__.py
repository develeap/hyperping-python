"""Pydantic models for Hyperping API requests and responses.

Public surface is identical to the previous ``models.py`` module.
All names importable from ``hyperping.models`` before this refactor remain
importable from this package with zero breakage.

Deprecated aliases (``IncidentStatus``, ``IncidentUpdateCreate``) are still
accessible but emit a :class:`DeprecationWarning` on first import. They will
be removed in v0.3.0.
"""

from hyperping.models._healthcheck_models import (
    Healthcheck,
    HealthcheckCreate,
    HealthcheckUpdate,
)
from hyperping.models._incident_models import (
    AddIncidentUpdateRequest,
    Incident,
    IncidentCreate,
    IncidentType,
    IncidentUpdate,
    IncidentUpdateRequest,
    IncidentUpdateType,
)
from hyperping.models._maintenance_models import (
    Maintenance,
    MaintenanceCreate,
    MaintenanceUpdate,
    NotificationOption,
)
from hyperping.models._monitor_models import (
    DEFAULT_REGIONS,
    APIErrorResponse,
    DnsRecordType,
    HttpMethod,
    LocalizedText,
    Monitor,
    MonitorBase,
    MonitorCreate,
    MonitorFrequency,
    MonitorListResponse,
    MonitorProtocol,
    MonitorReport,
    MonitorTimeout,
    MonitorUpdate,
    OutageDetail,
    OutageStats,
    Region,
    ReportPeriod,
    RequestHeader,
)
from hyperping.models._outage_models import Outage, OutageAction
from hyperping.models._statuspage_models import (
    StatusPage,
    StatusPageCreate,
    StatusPageSubscriber,
    StatusPageUpdate,
)

__all__ = [
    # Shared primitives
    "LocalizedText",
    "RequestHeader",
    # Monitor enums
    "HttpMethod",
    "MonitorFrequency",
    "MonitorTimeout",
    "Region",
    "MonitorProtocol",
    "DnsRecordType",
    "DEFAULT_REGIONS",
    # Monitor models
    "MonitorBase",
    "Monitor",
    "MonitorCreate",
    "MonitorUpdate",
    "MonitorReport",
    "MonitorListResponse",
    # Report sub-models
    "ReportPeriod",
    "OutageDetail",
    "OutageStats",
    # Error response model (intentionally internal — not returned by any client method)
    "APIErrorResponse",
    # Incident models
    "AddIncidentUpdateRequest",
    "Incident",
    "IncidentCreate",
    "IncidentType",
    "IncidentUpdate",
    "IncidentUpdateRequest",
    "IncidentUpdateType",
    # Deprecated aliases (emit DeprecationWarning on access, removed in v0.3.0)
    "IncidentStatus",
    "IncidentUpdateCreate",
    # Maintenance models
    "Maintenance",
    "MaintenanceCreate",
    "MaintenanceUpdate",
    "NotificationOption",
    # Outage models
    "Outage",
    "OutageAction",
    # Healthcheck models
    "Healthcheck",
    "HealthcheckCreate",
    "HealthcheckUpdate",
    # Status page models
    "StatusPage",
    "StatusPageCreate",
    "StatusPageUpdate",
    "StatusPageSubscriber",
]


def __getattr__(name: str) -> object:
    """Provide deprecated aliases with DeprecationWarning (L3).

    ``IncidentStatus`` and ``IncidentUpdateCreate`` are legacy names kept for
    backward compatibility. They will be removed in v0.3.0.
    """
    import warnings

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
    raise AttributeError(f"module 'hyperping.models' has no attribute {name!r}")
