"""High-level typed MCP client for the Hyperping MCP server.

Wraps :class:`~hyperping._mcp_transport.McpTransport` with typed convenience
methods that mirror the MCP tool names exposed by the server.

Example::

    from hyperping import HyperpingMcpClient

    with HyperpingMcpClient(api_key="sk_...") as mcp:
        summary = mcp.get_status_summary()
        print(summary.total, summary.up, summary.down)
"""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from hyperping._mcp_transport import McpTransport
from hyperping.endpoints import MCP_URL
from hyperping.models._integration_models import Integration
from hyperping.models._monitor_models import Monitor
from hyperping.models._observability_models import MonitorAnomaly, ProbeLogResponse
from hyperping.models._oncall_models import EscalationPolicy, OnCallSchedule, TeamMember
from hyperping.models._outage_models import OutageTimeline
from hyperping.models._reporting_models import (
    AlertHistory,
    MttaReport,
    MttrReport,
    ResponseTimeReport,
    StatusSummary,
)


class HyperpingMcpClient:
    """High-level client for Hyperping MCP server tools.

    Provides typed convenience methods for every MCP tool. Methods return
    Pydantic models matching the verified API response shapes.

    Supports the same ``api_key`` formats (``str`` or ``SecretStr``) and
    context-manager pattern as :class:`~hyperping.client.HyperpingClient`.
    """

    def __init__(
        self,
        api_key: str | SecretStr,
        base_url: str = MCP_URL,
        timeout: float = 30.0,
        allow_insecure: bool = False,
    ) -> None:
        self._transport = McpTransport(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            allow_insecure=allow_insecure,
        )

    # ==================== Internal ====================

    def _call(self, tool: str, args: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool via the transport."""
        return self._transport.call_tool(tool, args or {})

    def ensure_initialized(self) -> None:
        """Perform the MCP handshake now if it hasn't happened yet.

        Useful for startup health checks: call this once on boot and catch
        :class:`HyperpingRateLimitError` so you can decide whether to start
        the rest of your service. Subsequent tool calls reuse the handshake.

        Idempotent: calling it more than once is a no-op after success.

        Raises:
            HyperpingRateLimitError: If the server rate-limits ``initialize``,
                either via HTTP 429 or via the JSON-RPC ``-32000`` rate-limit
                payload. Inspect ``.retry_after`` to back off.
            HyperpingAuthError: If the API key is invalid (HTTP 401/403).
            HyperpingNotFoundError: If the MCP endpoint URL is wrong
                (HTTP 404).
            HyperpingValidationError: If the server rejects the handshake
                payload (HTTP 400/422; unusual on initialize).
            HyperpingAPIError: Any other transport-level error (HTTP 5xx,
                malformed body, etc.).
        """
        self._transport.initialize()

    # ==================== Context Manager ====================

    def close(self) -> None:
        """Close the underlying HTTP transport."""
        self._transport.close()

    def __enter__(self) -> HyperpingMcpClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ==================== Status & Reporting ====================

    def get_status_summary(self) -> StatusSummary:
        """Get aggregate monitor status counts."""
        return StatusSummary.model_validate(self._call("get_status_summary"))

    def get_monitor_response_time(
        self,
        monitor_uuid: str,
        **kwargs: Any,
    ) -> ResponseTimeReport:
        """Get response time metrics for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        return ResponseTimeReport.model_validate(
            self._call("get_monitor_response_time", {"uuid": monitor_uuid, **kwargs})
        )

    def get_monitor_mtta(
        self,
        monitor_uuid: str | None = None,
        **kwargs: Any,
    ) -> MttaReport:
        """Get mean time to acknowledge metrics.

        Args:
            monitor_uuid: Optional monitor UUID to scope the query.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        args: dict[str, Any] = {**kwargs}
        if monitor_uuid is not None:
            args["uuid"] = monitor_uuid
        return MttaReport.model_validate(self._call("get_monitor_mtta", args))

    def get_monitor_mttr(
        self,
        monitor_uuid: str | None = None,
        **kwargs: Any,
    ) -> MttrReport:
        """Get mean time to resolve metrics.

        Args:
            monitor_uuid: Optional monitor UUID to scope the query.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        args: dict[str, Any] = {**kwargs}
        if monitor_uuid is not None:
            args["uuid"] = monitor_uuid
        return MttrReport.model_validate(self._call("get_monitor_mttr", args))

    # ==================== Observability ====================

    def get_monitor_anomalies(self, monitor_uuid: str) -> list[MonitorAnomaly]:
        """Get anomalies detected for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
        """
        data = self._call("get_monitor_anomalies", {"uuid": monitor_uuid})
        raw = data.get("anomalies", []) if isinstance(data, dict) else []
        return [MonitorAnomaly.model_validate(a) for a in raw]

    def get_monitor_http_logs(
        self,
        monitor_uuid: str,
        **kwargs: Any,
    ) -> ProbeLogResponse:
        """Get HTTP probe logs for a monitor.

        Args:
            monitor_uuid: Monitor UUID.
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        data = self._call("get_monitor_http_logs", {"uuid": monitor_uuid, **kwargs})
        return ProbeLogResponse.model_validate(data)

    # ==================== Alerts ====================

    def list_recent_alerts(self, **kwargs: Any) -> AlertHistory:
        """List recent alert notifications.

        Args:
            **kwargs: Additional arguments forwarded to the MCP tool.
        """
        return AlertHistory.model_validate(self._call("list_recent_alerts", {**kwargs}))

    # ==================== On-Call ====================

    def list_on_call_schedules(self) -> list[OnCallSchedule]:
        """List all on-call schedules."""
        data = self._call("list_on_call_schedules")
        raw = data.get("schedules", []) if isinstance(data, dict) else []
        return [OnCallSchedule.model_validate(s) for s in raw]

    def get_on_call_schedule(self, uuid: str) -> OnCallSchedule:
        """Get a single on-call schedule by UUID.

        Args:
            uuid: Schedule UUID.
        """
        return OnCallSchedule.model_validate(self._call("get_on_call_schedule", {"uuid": uuid}))

    # ==================== Escalation Policies ====================

    def list_escalation_policies(self) -> list[EscalationPolicy]:
        """List all escalation policies."""
        data = self._call("list_escalation_policies")
        raw = data if isinstance(data, list) else []
        return [EscalationPolicy.model_validate(p) for p in raw]

    def get_escalation_policy(self, uuid: str) -> EscalationPolicy:
        """Get a single escalation policy by UUID.

        Args:
            uuid: Escalation policy UUID.
        """
        return EscalationPolicy.model_validate(self._call("get_escalation_policy", {"uuid": uuid}))

    # ==================== Team ====================

    def list_team_members(self) -> list[TeamMember]:
        """List all team members."""
        data = self._call("list_team_members")
        raw = data if isinstance(data, list) else []
        return [TeamMember.model_validate(m) for m in raw]

    # ==================== Integrations ====================

    def list_integrations(self) -> list[Integration]:
        """List all notification channel integrations."""
        data = self._call("list_integrations")
        raw = data if isinstance(data, list) else []
        return [Integration.model_validate(i) for i in raw]

    def get_integration(self, uuid: str) -> Integration:
        """Get a single integration by UUID.

        Args:
            uuid: Integration UUID.
        """
        return Integration.model_validate(self._call("get_integration", {"uuid": uuid}))

    # ==================== Outages ====================

    def get_outage_timeline(self, outage_uuid: str) -> OutageTimeline:
        """Get the lifecycle timeline for an outage.

        Args:
            outage_uuid: Outage UUID.
        """
        return OutageTimeline.model_validate(
            self._call("get_outage_timeline", {"uuid": outage_uuid})
        )

    # ==================== Monitors ====================

    def search_monitors_by_name(self, query: str) -> list[Monitor]:
        """Search monitors by name.

        Args:
            query: Search string to match against monitor names.
        """
        data = self._call("search_monitors_by_name", {"query": query})
        raw = data if isinstance(data, list) else []
        return [Monitor.model_validate(m) for m in raw]
