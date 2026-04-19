"""On-call mixin: schedules, escalation policies, team members."""

from typing import Any

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingAPIError, HyperpingNotFoundError
from hyperping.models._oncall_models import EscalationPolicy, OnCallSchedule


class OnCallMixin(_ClientProtocol):
    """On-call context API operations."""

    def list_on_call_schedules(self) -> list[OnCallSchedule]:
        """Get all on-call rotation schedules.

        Returns:
            List of :class:`~hyperping.models.OnCallSchedule` objects.
            Returns empty list on 404.
        """
        try:
            result = self._request("GET", Endpoint.ON_CALL_SCHEDULES)
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, OnCallSchedule, "on_call_schedule")

    def get_on_call_schedule(self, schedule_id: str) -> OnCallSchedule:
        """Get a single on-call schedule.

        Args:
            schedule_id: Schedule UUID.

        Returns:
            :class:`~hyperping.models.OnCallSchedule` object.

        Raises:
            HyperpingNotFoundError: If schedule not found.
        """
        validate_id(schedule_id, "schedule_id")
        result = self._request("GET", f"{Endpoint.ON_CALL_SCHEDULES}/{schedule_id}")
        return OnCallSchedule.model_validate(expect_dict(result, "get_on_call_schedule"))

    def list_escalation_policies(self) -> list[EscalationPolicy]:
        """Get all escalation policies.

        Returns:
            List of :class:`~hyperping.models.EscalationPolicy` objects.
            Returns empty list on 404.
        """
        try:
            result = self._request("GET", Endpoint.ESCALATION_POLICIES)
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, EscalationPolicy, "escalation_policy")

    def get_escalation_policy(self, policy_id: str) -> EscalationPolicy:
        """Get a single escalation policy.

        Args:
            policy_id: Policy UUID.

        Returns:
            :class:`~hyperping.models.EscalationPolicy` object.

        Raises:
            HyperpingNotFoundError: If policy not found.
        """
        validate_id(policy_id, "policy_id")
        result = self._request("GET", f"{Endpoint.ESCALATION_POLICIES}/{policy_id}")
        return EscalationPolicy.model_validate(expect_dict(result, "get_escalation_policy"))

    def list_team_members(self) -> list[dict[str, Any]]:
        """Get all team members.

        Returns:
            List of dicts with member info (name, email).
            Returns empty list on 404.
        """
        try:
            result = self._request("GET", Endpoint.TEAM_MEMBERS)
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        if isinstance(result, list):
            return result
        return []
