"""Async on-call mixin: schedules, escalation policies, team members."""

from typing import Any

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models._oncall_models import EscalationPolicy, OnCallSchedule


class AsyncOnCallMixin(_AsyncClientProtocol):
    """Async on-call context API operations."""

    async def list_on_call_schedules(self) -> list[OnCallSchedule]:
        """Get all on-call rotation schedules."""
        try:
            result = await self._request("GET", Endpoint.ON_CALL_SCHEDULES)
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, OnCallSchedule, "on_call_schedule")

    async def get_on_call_schedule(self, schedule_id: str) -> OnCallSchedule:
        """Get a single on-call schedule."""
        validate_id(schedule_id, "schedule_id")
        result = await self._request("GET", f"{Endpoint.ON_CALL_SCHEDULES}/{schedule_id}")
        return OnCallSchedule.model_validate(expect_dict(result, "get_on_call_schedule"))

    async def list_escalation_policies(self) -> list[EscalationPolicy]:
        """Get all escalation policies."""
        try:
            result = await self._request("GET", Endpoint.ESCALATION_POLICIES)
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, EscalationPolicy, "escalation_policy")

    async def get_escalation_policy(self, policy_id: str) -> EscalationPolicy:
        """Get a single escalation policy."""
        validate_id(policy_id, "policy_id")
        result = await self._request("GET", f"{Endpoint.ESCALATION_POLICIES}/{policy_id}")
        return EscalationPolicy.model_validate(expect_dict(result, "get_escalation_policy"))

    async def list_team_members(self) -> list[dict[str, Any]]:
        """Get all team members."""
        try:
            result = await self._request("GET", Endpoint.TEAM_MEMBERS)
        except Exception:
            return []
        if isinstance(result, list):
            return result
        return []
