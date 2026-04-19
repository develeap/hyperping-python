"""Async integrations mixin: notification channel management."""

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import expect_dict, parse_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models._integration_models import Integration


class AsyncIntegrationsMixin(_AsyncClientProtocol):
    """Async integration API operations."""

    async def list_integrations(self) -> list[Integration]:
        """Get all configured notification integrations."""
        try:
            result = await self._request("GET", Endpoint.INTEGRATIONS)
        except Exception:
            return []
        items = result if isinstance(result, list) else []
        return parse_list(items, Integration, "integration")

    async def get_integration(self, integration_id: str) -> Integration:
        """Get a single integration."""
        validate_id(integration_id, "integration_id")
        result = await self._request("GET", f"{Endpoint.INTEGRATIONS}/{integration_id}")
        return Integration.model_validate(expect_dict(result, "get_integration"))
