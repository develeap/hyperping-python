"""Integrations mixin: notification channel management."""

from hyperping._protocols import _ClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.exceptions import HyperpingAPIError, HyperpingNotFoundError
from hyperping.models._integration_models import Integration


class IntegrationsMixin(_ClientProtocol):
    """Integration API operations."""

    def list_integrations(self) -> list[Integration]:
        """Get all configured notification integrations.

        Returns:
            List of :class:`~hyperping.models.Integration` objects.
            Returns empty list on 404.
        """
        try:
            result = self._request("GET", Endpoint.INTEGRATIONS)
        except (HyperpingNotFoundError, HyperpingAPIError):
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, Integration, "integration")

    def get_integration(self, integration_id: str) -> Integration:
        """Get a single integration.

        Args:
            integration_id: Integration UUID.

        Returns:
            :class:`~hyperping.models.Integration` object.

        Raises:
            HyperpingNotFoundError: If integration not found.
        """
        validate_id(integration_id, "integration_id")
        result = self._request("GET", f"{Endpoint.INTEGRATIONS}/{integration_id}")
        return Integration.model_validate(expect_dict(result, "get_integration"))
