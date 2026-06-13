#!/usr/bin/env python3
"""Probe on-call schedules via the MCP client.

Verifies that the 'SDK-Verification' on-call schedule exists and is
reachable via list_on_call_schedules / get_on_call_schedule.

Usage:
    export HYPERPING_API_KEY=sk_...    # or HYPERPING_TEST_API_KEY for test account
    python scripts/probe_on_call.py

Exit code 0 = all criteria met; exit code 1 = schedule missing or probe failed.

If the schedule does not exist, create it through the Hyperping web UI:
  - Name: SDK-Verification
  - Rotations: 1
  - Frequency: daily
  - Keep the schedule permanently for future regression probes.
"""

import os
import sys

from hyperping import HyperpingMcpClient

_SCHEDULE_NAME = "SDK-Verification"


def main() -> int:
    api_key = os.environ.get("HYPERPING_API_KEY") or os.environ.get("HYPERPING_TEST_API_KEY")
    if not api_key:
        print("ERROR: Set HYPERPING_API_KEY (or HYPERPING_TEST_API_KEY).")
        return 1

    with HyperpingMcpClient(api_key=api_key) as mcp:
        print("Probing list_on_call_schedules ...")
        schedules = mcp.list_on_call_schedules()

        if not schedules:
            print(
                "FAIL: list_on_call_schedules returned an empty array.\n"
                f"      Create '{_SCHEDULE_NAME}' through the Hyperping web UI and re-run."
            )
            return 1

        target = next((s for s in schedules if s.name == _SCHEDULE_NAME), None)
        if target is None:
            names = ", ".join(s.name for s in schedules)
            print(
                f"FAIL: No schedule named '{_SCHEDULE_NAME}' found.\n"
                f"      Existing schedules: {names}\n"
                f"      Create '{_SCHEDULE_NAME}' through the Hyperping web UI and re-run."
            )
            return 1

        print(f"OK:   Found schedule '{target.name}' (uuid={target.uuid})")

        print(f"Probing get_on_call_schedule({target.uuid!r}) ...")
        fetched = mcp.get_on_call_schedule(target.uuid)
        if fetched.uuid != target.uuid:
            print(f"FAIL: get_on_call_schedule returned mismatched UUID: {fetched.uuid}")
            return 1

        print(f"OK:   get_on_call_schedule confirmed uuid={fetched.uuid}")

    print("\nAll acceptance criteria satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
