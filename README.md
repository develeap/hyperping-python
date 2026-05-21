# hyperping

[![PyPI version](https://img.shields.io/pypi/v/hyperping)](https://pypi.org/project/hyperping/)
[![Python versions](https://img.shields.io/pypi/pyversions/hyperping)](https://pypi.org/project/hyperping/#history)
[![CI](https://github.com/develeap/hyperping-python/actions/workflows/ci.yml/badge.svg)](https://github.com/develeap/hyperping-python/actions/workflows/ci.yml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://www.mypy-lang.org/static/mypy_badge.svg)](https://mypy-lang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK for the [Hyperping](https://hyperping.io) uptime monitoring and incident management API.

## Installation

Requires **Python 3.11+**.

```bash
pip install hyperping
# or
uv add hyperping
```

## Quick Start

```python
from hyperping import HyperpingClient, IncidentCreate, LocalizedText

with HyperpingClient(api_key="sk_...") as client:
    # List all monitors
    monitors = client.list_monitors()
    for m in monitors:
        print(f"{m.name}: {'down' if m.down else 'up'}")

    # Open an incident
    incident = client.create_incident(
        IncidentCreate(
            title=LocalizedText(en="Service degradation"),
            text=LocalizedText(en="Investigating elevated error rates"),
            statuspages=["sp_your_uuid"],
        )
    )

    # Resolve it
    client.resolve_incident(incident.uuid, "All systems operational")
```

## Async Client

An async-first client is available for use with `asyncio` and `anyio`-based frameworks:

```python
from hyperping import AsyncHyperpingClient

async def main():
    async with AsyncHyperpingClient(api_key="sk_...") as client:
        monitors = await client.list_monitors()
        for m in monitors:
            print(f"{m.name}: {'down' if m.down else 'up'}")

        outage = await client.acknowledge_outage("out_uuid", message="On it")
```

The async client supports all the same resources, retry behaviour, and circuit breaker as the sync client. Use `RetryConfig` and `CircuitBreakerConfig` in exactly the same way.

An async MCP client is also available:

```python
from hyperping import AsyncHyperpingMcpClient

async def main():
    async with AsyncHyperpingMcpClient(api_key="sk_...") as mcp:
        summary = await mcp.get_status_summary()
        members = await mcp.list_team_members()
        anomalies = await mcp.get_monitor_anomalies("mon_uuid")
```

## Authentication

Pass your API key directly or via environment variable:

```python
import os
from hyperping import HyperpingClient

# Constructor param
client = HyperpingClient(api_key="sk_...")

# From environment
client = HyperpingClient(api_key=os.environ["HYPERPING_API_KEY"])
```

## Resources

### Monitors

```python
monitors = client.list_monitors()
monitor  = client.get_monitor("mon_uuid")
created  = client.create_monitor(MonitorCreate(name="API", url="https://api.example.com"))
client.pause_monitor("mon_uuid")
client.resume_monitor("mon_uuid")
client.delete_monitor("mon_uuid")

# Reports
reports = client.get_all_reports(period="30d")
report  = client.get_monitor_report("mon_uuid", period="7d")
```

### Incidents

```python
incidents = client.list_incidents()
incident  = client.get_incident("inci_uuid")
created   = client.create_incident(IncidentCreate(...))
client.add_incident_update("inci_uuid", AddIncidentUpdateRequest(...))
client.resolve_incident("inci_uuid", "Fixed")
client.delete_incident("inci_uuid")
```

### Maintenance Windows

```python
windows = client.list_maintenance()
window  = client.get_maintenance("mw_uuid")
created = client.create_maintenance(MaintenanceCreate(...))
client.update_maintenance("mw_uuid", MaintenanceUpdate(name="New name"))
client.delete_maintenance("mw_uuid")

# Helpers
active = client.get_active_maintenance()
in_maint = client.is_monitor_in_maintenance("mon_uuid")
```

### Outages

```python
outages = client.list_outages()              # auto-fetches all pages
outages = client.list_outages(page=0)        # single page
client.acknowledge_outage("out_uuid", message="On it")
client.resolve_outage("out_uuid", message="Fixed")
client.escalate_outage("out_uuid")
```

### Status Pages

```python
pages = client.list_status_pages(search="prod")    # auto-fetches all pages
pages = client.list_status_pages(page=0)            # single page
page  = client.get_status_page("sp_uuid")
created = client.create_status_page(StatusPageCreate(name="Prod", subdomain="prod-status"))
client.update_status_page("sp_uuid", StatusPageUpdate(name="Production Status"))
client.delete_status_page("sp_uuid")

# Subscribers
subs = client.list_subscribers("sp_uuid")           # auto-fetches all pages
sub  = client.add_subscriber("sp_uuid", "user@example.com")
client.remove_subscriber("sp_uuid", sub.id)
```

### MCP Client (on-call, alerts, anomalies, integrations)

Some Hyperping features are only available via the MCP server (JSON-RPC 2.0),
not the REST API. Use `HyperpingMcpClient` for these:

```python
from hyperping import HyperpingMcpClient

with HyperpingMcpClient(api_key="sk_...") as mcp:
    # Status & reporting
    summary = mcp.get_status_summary()
    mtta = mcp.get_monitor_mtta("mon_uuid")
    mttr = mcp.get_monitor_mttr("mon_uuid")
    response_time = mcp.get_monitor_response_time("mon_uuid")

    # On-call & escalation
    schedules = mcp.list_on_call_schedules()
    policies = mcp.list_escalation_policies()
    members = mcp.list_team_members()

    # Observability
    anomalies = mcp.get_monitor_anomalies("mon_uuid")
    logs = mcp.get_monitor_http_logs("mon_uuid")
    alerts = mcp.list_recent_alerts()

    # Integrations
    integrations = mcp.list_integrations()

    # Outage timeline & monitor search
    timeline = mcp.get_outage_timeline("out_uuid")
    results = mcp.search_monitors_by_name("api")
```

The MCP client uses the same API key as `HyperpingClient`. All methods return
plain dicts/lists; use the exported Pydantic models (e.g., `OnCallSchedule`,
`EscalationPolicy`) for validation if needed.

### MCP rate limits and connection lifecycle

The Hyperping MCP server (`https://api.hyperping.io/v1/mcp`) is
[documented by Hyperping as stateless over HTTP](https://hyperping.com/mcp)
and rate-limits per API key. The publicly documented limit is 300 requests per
minute shared with the REST API
([rate-limit docs](https://hyperping.com/docs/monitoring/api-rate-limits)), but
the server also enforces a separate, undocumented cap on the `initialize`
handshake (observed around 5/minute). Because every new `HyperpingMcpClient`
instance must perform the MCP `initialize` handshake on its first call,
instantiating the client in a hot path or running several short-lived processes
against one key will trip this cap.

Operational guidance:

- **Create one `HyperpingMcpClient` per process and reuse it.** Do not instantiate
  it inside a loop. The first call performs the handshake; subsequent calls reuse
  it for the life of the client.
- **Catch `HyperpingRateLimitError` and honour `retry_after`.** Rate-limit signals
  arrive two ways: as HTTP 429 (with a standard `Retry-After` header) and as a
  JSON-RPC server error (`code: -32000`, HTTP 200) on `initialize`. Both surface as
  `HyperpingRateLimitError` with `retry_after` parsed from whichever signal was
  used. The `status_code` attribute is `429` or `200`, matching the underlying
  signal; cool-off short-circuits preserve the originating status code so callers
  can disambiguate the two buckets.
- **Use `ensure_initialized()` for startup health checks.** Calling it once on
  service boot lets you fail fast if the key is already at the `initialize` cap,
  instead of failing on the first business call.
- **Several workloads on one key collide on the `initialize` cap.** A weekly cron,
  a watchdog daemon, and a developer running the CLI cannot all warm up the same
  API key inside one minute. Use one long-lived process per workload, or separate
  API keys per workload if your plan allows.
- **After a rate-limit on `initialize`, the SDK latches a cool-off** so that
  subsequent `call_tool` invocations on the same client fail fast with
  `HyperpingRateLimitError` (no extra HTTP traffic) until `retry_after` elapses.
  This prevents accidentally burning more slots from the bucket. The latch is
  per-`HyperpingMcpClient` instance and per-process; it does not coordinate
  across separate Python processes sharing the same API key, so multi-process
  setups still need the workload-separation advice above.

```python
from hyperping import HyperpingMcpClient, HyperpingRateLimitError

mcp = HyperpingMcpClient(api_key="sk_...")
try:
    mcp.ensure_initialized()
except HyperpingRateLimitError as e:
    print(f"MCP cold-start rate-limited; retry in {e.retry_after}s")
    raise

summary = mcp.get_status_summary()
```

### Healthchecks

```python
checks = client.list_healthchecks()
check  = client.get_healthcheck("hc_uuid")
created = client.create_healthcheck(HealthcheckCreate(name="Nightly Job", period=86400, grace=3600))
client.update_healthcheck("hc_uuid", HealthcheckUpdate(grace=7200))
client.pause_healthcheck("hc_uuid")
client.resume_healthcheck("hc_uuid")
client.delete_healthcheck("hc_uuid")
```

## Error Handling

```python
from hyperping import (
    HyperpingAPIError,
    HyperpingAuthError,
    HyperpingNotFoundError,
    HyperpingRateLimitError,
    HyperpingValidationError,
)

try:
    monitor = client.get_monitor("mon_uuid")
except HyperpingNotFoundError:
    print("Monitor not found")
except HyperpingRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except HyperpingAuthError:
    print("Invalid API key")
except HyperpingAPIError as e:
    print(f"API error [{e.status_code}]: {e.message}")
    print(f"Request ID: {e.request_id}")
```

## Retries and Circuit Breaker

The SDK retries automatically on transient errors (5xx, 429) with exponential backoff and jitter. A circuit breaker prevents cascading failures.

```python
from hyperping import HyperpingClient
from hyperping.client import RetryConfig, CircuitBreakerConfig

client = HyperpingClient(
    api_key="sk_...",
    retry_config=RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        backoff_factor=2.0,
    ),
    circuit_breaker_config=CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=60.0,
    ),
)
```

### Per-endpoint circuit breaker

By default a single shared circuit breaker covers every request. If one endpoint flakes, every other endpoint is also blocked. Enable `per_endpoint_circuit_breaker=True` to keep one breaker per *endpoint* so a failing endpoint does not punish healthy ones:

```python
client = HyperpingClient(
    api_key="sk_...",
    per_endpoint_circuit_breaker=True,
)

# Inspect state for an endpoint. The breaker key is canonicalised to the
# matching `Endpoint` prefix, so all sub-resource paths share a bucket:
from hyperping import CircuitState, Endpoint

state = client.circuit_breaker_state_for(str(Endpoint.MONITORS))
# /v1/monitors, /v1/monitors/mon_abc and /v1/monitors/mon_abc/reports all
# report the same state — they share the `/v1/monitors` breaker.
assert client.circuit_breaker_state_for(f"{Endpoint.MONITORS}/mon_abc") == state
assert state in {CircuitState.CLOSED, CircuitState.HALF_OPEN, CircuitState.OPEN}
```

If you need different bucketing (e.g. one breaker per resource UUID, or a single breaker per HTTP verb), pass a `breaker_key_fn`:

```python
def per_resource(path: str) -> str:
    # one breaker per literal request path
    return path.split("?", 1)[0]

client = HyperpingClient(
    api_key="sk_...",
    per_endpoint_circuit_breaker=True,
    breaker_key_fn=per_resource,
)
```

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `per_endpoint_circuit_breaker` | `bool` | `False` | When `True`, maintain a separate circuit breaker keyed by request endpoint instead of using one shared breaker. The same `circuit_breaker_config` applies to every per-endpoint breaker. The shared breaker remains accessible via `client.circuit_breaker`. |
| `breaker_key_fn` | `Callable[[str], str] \| None` | `None` | Override the default endpoint-prefix bucketing. Receives the request path and returns the breaker key. Default behaviour collapses every path under the matching `Endpoint` prefix so the breaker set stays bounded (one per `Endpoint`); a custom function takes responsibility for keeping the key set bounded. Ignored unless `per_endpoint_circuit_breaker=True`. |

State for any path is readable via `client.circuit_breaker_state_for(path)`. In the default (single-breaker) mode this returns the shared breaker's state for any path, so the call is always safe regardless of the flag. The same options and method are available on `AsyncHyperpingClient`.

## Type Safety

This package ships a `py.typed` marker (PEP 561) and is fully typed. Works out of the box with mypy and pyright.

## Contributing

See [CONTRIBUTING.md](https://github.com/develeap/hyperping-python/blob/main/CONTRIBUTING.md).

## License

MIT — see [LICENSE](https://github.com/develeap/hyperping-python/blob/main/LICENSE).

## Maintained by

[Develeap](https://develeap.com)
