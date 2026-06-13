#!/usr/bin/env python3
"""Verify speculative MCP-discovered endpoint paths against the live Hyperping API.

Usage:
    export HYPERPING_API_KEY=sk_...
    python scripts/verify_endpoints.py

All calls are read-only (GET only). Safe to run repeatedly.
"""

import os
import sys
from dataclasses import dataclass

import httpx

API_BASE = "https://api.hyperping.io"


@dataclass
class Result:
    method: str
    path: str
    status: int
    ok: bool
    snippet: str


def probe(
    client: httpx.Client,
    method_name: str,
    path: str,
    params: dict | None = None,
) -> Result:
    """Send a GET request and return a Result."""
    url = f"{API_BASE}{path}"
    try:
        resp = client.get(url, params=params or {})
        body = resp.text[:120].replace("\n", " ")
        return Result(
            method=method_name,
            path=path,
            status=resp.status_code,
            ok=resp.status_code < 400,
            snippet=body,
        )
    except httpx.HTTPError as exc:
        return Result(
            method=method_name,
            path=path,
            status=0,
            ok=False,
            snippet=f"Connection error: {exc}",
        )


def main() -> int:
    api_key = os.environ.get("HYPERPING_API_KEY", "")
    if not api_key:
        print("ERROR: Set HYPERPING_API_KEY environment variable.")
        return 1

    headers = {"Authorization": f"Bearer {api_key}"}
    client = httpx.Client(headers=headers, timeout=15.0)

    # -- Fetch real UUIDs for sub-resource endpoints --
    print("Fetching monitor and outage UUIDs for sub-resource tests...")
    monitor_uuid: str | None = None
    outage_uuid: str | None = None

    resp = client.get(f"{API_BASE}/v1/monitors")
    if resp.status_code == 200:
        data = resp.json()
        monitors = data if isinstance(data, list) else data.get("monitors", [])
        if monitors:
            monitor_uuid = monitors[0].get("uuid") or monitors[0].get("id")
            print(f"  Monitor UUID: {monitor_uuid}")

    resp = client.get(f"{API_BASE}/v2/outages")
    if resp.status_code == 200:
        data = resp.json()
        outages = data if isinstance(data, list) else data.get("outages", [])
        if outages:
            outage_uuid = outages[0].get("uuid") or outages[0].get("id")
            print(f"  Outage UUID:  {outage_uuid}")

    print()

    # -- Define all speculative endpoints to verify --
    checks: list[tuple[str, str, dict | None]] = [
        # Endpoint enum speculative paths
        ("get_status_summary", "/v2/status-summary", None),
        ("list_recent_alerts", "/v2/alerts", None),
        ("list_on_call_schedules", "/v2/on-call-schedules", None),
        ("list_escalation_policies", "/v2/escalation-policies", None),
        ("list_team_members", "/v2/team-members", None),
        ("list_integrations", "/v2/integrations", None),
        # Monitor search
        ("search_monitors", "/v1/monitors/search", {"query": "test"}),
        # Speculative project endpoints (ticket #7117f0)
        ("list_projects_v1", "/v1/projects", None),
        ("list_projects_v2", "/v2/projects", None),
    ]

    # Sub-resource paths needing a real UUID
    if monitor_uuid:
        checks.extend([
            (
                "get_monitor_response_time",
                f"/v2/reporting/response-time/{monitor_uuid}",
                {"period": "24h"},
            ),
            (
                "get_monitor_mtta",
                f"/v2/reporting/mtta/{monitor_uuid}",
                {"period": "30d"},
            ),
            (
                "get_monitor_anomalies",
                f"/v1/monitors/{monitor_uuid}/anomalies",
                None,
            ),
            (
                "get_monitor_http_logs",
                f"/v1/monitors/{monitor_uuid}/http-logs",
                {"page": "0", "limit": "5"},
            ),
        ])
    else:
        print("WARNING: No monitors found; skipping monitor sub-resource checks.\n")

    if outage_uuid:
        checks.append((
            "get_outage_timeline",
            f"/v2/outages/{outage_uuid}/timeline",
            None,
        ))
    else:
        print("WARNING: No outages found; skipping outage sub-resource checks.\n")

    # -- Run probes --
    results: list[Result] = []
    for method_name, path, params in checks:
        r = probe(client, method_name, path, params)
        results.append(r)

    client.close()

    # -- Print results table --
    print(f"{'Method':<30} {'Path':<50} {'Status':<8} {'Result'}")
    print("-" * 120)
    for r in results:
        tag = "OK" if r.ok else ("404" if r.status == 404 else "ERROR")
        print(f"{r.method:<30} {r.path:<50} {r.status:<8} {tag}")
        if not r.ok:
            print(f"  {r.snippet}")

    # -- Summary --
    ok_count = sum(1 for r in results if r.ok)
    fail_count = sum(1 for r in results if not r.ok)
    not_found = sum(1 for r in results if r.status == 404)
    print()
    other_errors = fail_count - not_found
    print(
        f"Total: {len(results)} | OK: {ok_count} | 404: {not_found} | Other errors: {other_errors}"
    )

    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
