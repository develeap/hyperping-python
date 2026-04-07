"""Shared constants for monitor sync and async mixins.

Not part of the public API.
"""

# Valid period values for reporting endpoints (M9)
VALID_PERIODS: frozenset[str] = frozenset({"1h", "24h", "7d", "30d", "90d"})

# Writable fields for the Hyperping monitor PUT endpoint (M19)
MONITOR_WRITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "url",
        "protocol",
        "http_method",
        "check_frequency",
        "regions",
        "request_headers",
        "request_body",
        "follow_redirects",
        "expected_status_code",
        "required_keyword",
        "paused",
        "port",
        "alerts_wait",
        "escalation_policy",
        "dns_record_type",
        "dns_nameserver",
        "dns_expected_answer",
    }
)
