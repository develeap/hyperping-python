"""Tests for status page management API methods."""

import httpx
import pytest
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint
from hyperping.exceptions import HyperpingNotFoundError, HyperpingValidationError
from hyperping.models import (
    StatusPage,
    StatusPageCreate,
    StatusPageSubscriber,
    StatusPageUpdate,
)

# ==================== Model Tests ====================


class TestStatusPageModels:
    """Tests for StatusPage Pydantic models."""

    def test_status_page_parse(self) -> None:
        """Test parsing a status page API response."""
        data = {
            "uuid": "sp_abc123",
            "name": "My Status Page",
            "subdomain": "my-status",
            "public": True,
            "monitors": ["mon_1", "mon_2"],
        }
        page = StatusPage.model_validate(data)
        assert page.uuid == "sp_abc123"
        assert page.name == "My Status Page"
        assert page.subdomain == "my-status"
        assert page.public is True
        assert len(page.monitors) == 2

    def test_status_page_with_custom_domain(self) -> None:
        """Test parsing a status page with custom domain."""
        data = {
            "uuid": "sp_custom",
            "name": "Custom Domain Page",
            "subdomain": "custom-status",
            "customDomain": "status.mycompany.com",
            "public": True,
            "monitors": [],
        }
        page = StatusPage.model_validate(data)
        assert page.custom_domain == "status.mycompany.com"

    def test_status_page_is_frozen(self) -> None:
        """Test that StatusPage is immutable."""
        page = StatusPage(
            uuid="sp_1",
            name="Test",
            subdomain="test-status",
            monitors=[],
        )
        with pytest.raises(Exception):
            page.name = "Changed"  # type: ignore[misc]

    def test_status_page_create_minimal(self) -> None:
        """Test creating a StatusPageCreate with minimal fields."""
        create = StatusPageCreate(
            name="Test Page",
            subdomain="test-status",
        )
        assert create.name == "Test Page"
        assert create.subdomain == "test-status"
        assert create.public is True  # default
        assert create.monitors == []  # default

    def test_status_page_update_all_optional(self) -> None:
        """Test that StatusPageUpdate allows all-None (no-op update)."""
        update = StatusPageUpdate()
        dumped = update.model_dump(exclude_none=True)
        assert dumped == {}

    def test_status_page_subscriber_parse(self) -> None:
        """Test parsing a subscriber response."""
        data = {"id": "sub_123", "email": "user@example.com"}
        sub = StatusPageSubscriber.model_validate(data)
        assert sub.id == "sub_123"
        assert sub.email == "user@example.com"

    def test_status_page_subscriber_is_frozen(self) -> None:
        """Test that StatusPageSubscriber is immutable."""
        sub = StatusPageSubscriber(id="sub_1", email="a@example.com")
        with pytest.raises(Exception):
            sub.email = "b@example.com"  # type: ignore[misc]


# ==================== API Tests ====================


class TestStatusPagesAPIClient:
    """Tests for all 8 status page API endpoints."""

    # ---- GET /v2/statuspages ----

    @respx.mock
    def test_list_status_pages(self, client: HyperpingClient) -> None:
        """Test listing all status pages."""
        mock_response = [
            {
                "uuid": "sp_1",
                "name": "Main Status",
                "subdomain": "main-status",
                "public": True,
                "monitors": ["mon_1"],
            },
            {
                "uuid": "sp_2",
                "name": "Internal Status",
                "subdomain": "internal-status",
                "public": False,
                "monitors": [],
            },
        ]
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        pages = client.list_status_pages()
        assert len(pages) == 2
        assert pages[0].uuid == "sp_1"
        assert pages[1].uuid == "sp_2"

    @respx.mock
    def test_list_status_pages_with_search(self, client: HyperpingClient) -> None:
        """Test listing status pages with a search filter."""
        mock_response = [
            {
                "uuid": "sp_1",
                "name": "Main Status",
                "subdomain": "main-status",
                "public": True,
                "monitors": [],
            }
        ]
        route = respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        pages = client.list_status_pages(search="main")
        assert len(pages) == 1
        # Verify query param was passed
        assert "search=main" in str(route.calls[0].request.url)

    @respx.mock
    def test_list_status_pages_empty(self, client: HyperpingClient) -> None:
        """Test listing when no status pages exist."""
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(200, json=[])
        )
        pages = client.list_status_pages()
        assert pages == []

    @respx.mock
    def test_list_status_pages_dict_response(self, client: HyperpingClient) -> None:
        """Test listing when API returns wrapped dict."""
        mock_response = {
            "statuspages": [
                {
                    "uuid": "sp_1",
                    "name": "Main",
                    "subdomain": "main",
                    "public": True,
                    "monitors": [],
                }
            ]
        }
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        pages = client.list_status_pages()
        assert len(pages) == 1

    # ---- GET /v2/statuspages/{uuid} ----

    @respx.mock
    def test_get_status_page(self, client: HyperpingClient) -> None:
        """Test getting a single status page."""
        mock_response = {
            "uuid": "sp_abc",
            "name": "Production Status",
            "subdomain": "prod-status",
            "public": True,
            "monitors": ["mon_1", "mon_2"],
        }
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_abc").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        page = client.get_status_page("sp_abc")
        assert page.uuid == "sp_abc"
        assert page.name == "Production Status"
        assert len(page.monitors) == 2

    @respx.mock
    def test_get_status_page_not_found(self, client: HyperpingClient) -> None:
        """Test getting a non-existent status page."""
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.get_status_page("sp_nope")

    # ---- POST /v2/statuspages ----

    @respx.mock
    def test_create_status_page(self, client: HyperpingClient) -> None:
        """Test creating a new status page."""
        mock_response = {
            "uuid": "sp_new",
            "name": "New Page",
            "subdomain": "new-status",
            "public": True,
            "monitors": ["mon_1"],
        }
        respx.post(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(201, json=mock_response)
        )

        page = client.create_status_page(
            StatusPageCreate(
                name="New Page",
                subdomain="new-status",
                monitors=["mon_1"],
            )
        )
        assert page.uuid == "sp_new"
        assert page.name == "New Page"

    @respx.mock
    def test_create_status_page_validation_error(self, client: HyperpingClient) -> None:
        """Test creating a status page with invalid data."""
        respx.post(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(
                400,
                json={
                    "error": "Invalid subdomain",
                    "details": [{"field": "subdomain", "message": "already taken"}],
                },
            )
        )
        with pytest.raises(HyperpingValidationError):
            client.create_status_page(
                StatusPageCreate(name="Conflict", subdomain="taken-subdomain")
            )

    # ---- PUT /v2/statuspages/{uuid} ----

    @respx.mock
    def test_update_status_page(self, client: HyperpingClient) -> None:
        """Test updating a status page."""
        mock_response = {
            "uuid": "sp_1",
            "name": "Updated Name",
            "subdomain": "my-status",
            "public": True,
            "monitors": [],
        }
        respx.put(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        page = client.update_status_page("sp_1", StatusPageUpdate(name="Updated Name"))
        assert page.name == "Updated Name"

    @respx.mock
    def test_update_status_page_not_found(self, client: HyperpingClient) -> None:
        """Test updating a non-existent status page."""
        respx.put(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.update_status_page("sp_nope", StatusPageUpdate(name="Doesn't matter"))

    # ---- DELETE /v2/statuspages/{uuid} ----

    @respx.mock
    def test_delete_status_page(self, client: HyperpingClient) -> None:
        """Test deleting a status page."""
        respx.delete(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_del").mock(
            return_value=httpx.Response(204)
        )
        client.delete_status_page("sp_del")  # Should not raise

    @respx.mock
    def test_delete_status_page_not_found(self, client: HyperpingClient) -> None:
        """Test deleting a non-existent status page."""
        respx.delete(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_nope").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        with pytest.raises(HyperpingNotFoundError):
            client.delete_status_page("sp_nope")

    # ---- GET /v2/statuspages/{uuid}/subscribers ----

    @respx.mock
    def test_list_subscribers(self, client: HyperpingClient) -> None:
        """Test listing subscribers for a status page."""
        mock_response = [
            {"id": "sub_1", "email": "alice@example.com"},
            {"id": "sub_2", "email": "bob@example.com"},
        ]
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers").mock(
            return_value=httpx.Response(200, json=mock_response)
        )

        subs = client.list_subscribers("sp_1")
        assert len(subs) == 2
        assert subs[0].email == "alice@example.com"
        assert subs[1].email == "bob@example.com"

    @respx.mock
    def test_list_subscribers_empty(self, client: HyperpingClient) -> None:
        """Test listing when there are no subscribers."""
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers").mock(
            return_value=httpx.Response(200, json=[])
        )
        subs = client.list_subscribers("sp_1")
        assert subs == []

    @respx.mock
    def test_list_subscribers_wrapped_response(self, client: HyperpingClient) -> None:
        """Test listing when API returns wrapped response."""
        mock_response = {
            "subscribers": [{"id": "sub_1", "email": "carol@example.com"}]
        }
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers").mock(
            return_value=httpx.Response(200, json=mock_response)
        )
        subs = client.list_subscribers("sp_1")
        assert len(subs) == 1

    @respx.mock
    def test_list_subscribers_status_page_not_found(self, client: HyperpingClient) -> None:
        """Test listing subscribers when status page doesn't exist."""
        respx.get(
            f"{API_BASE}{Endpoint.STATUSPAGES}/sp_nope/subscribers"
        ).mock(return_value=httpx.Response(404, json={"error": "Not found"}))
        with pytest.raises(HyperpingNotFoundError):
            client.list_subscribers("sp_nope")

    # ---- POST /v2/statuspages/{uuid}/subscribers ----

    @respx.mock
    def test_add_subscriber(self, client: HyperpingClient) -> None:
        """Test adding a subscriber to a status page."""
        mock_response = {"id": "sub_new", "email": "dave@example.com"}
        respx.post(f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers").mock(
            return_value=httpx.Response(201, json=mock_response)
        )

        sub = client.add_subscriber("sp_1", "dave@example.com")
        assert sub.id == "sub_new"
        assert sub.email == "dave@example.com"

    def test_add_subscriber_invalid_email_raises_value_error(
        self, client: HyperpingClient
    ) -> None:
        """Test adding a subscriber with an invalid email raises ValueError (M10)."""
        with pytest.raises(ValueError, match="Invalid email"):
            client.add_subscriber("sp_1", "not-an-email")

    # ---- DELETE /v2/statuspages/{uuid}/subscribers/{id} ----

    @respx.mock
    def test_remove_subscriber(self, client: HyperpingClient) -> None:
        """Test removing a subscriber from a status page."""
        respx.delete(
            f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers/sub_1"
        ).mock(return_value=httpx.Response(204))

        client.remove_subscriber("sp_1", "sub_1")  # Should not raise

    @respx.mock
    def test_remove_subscriber_not_found(self, client: HyperpingClient) -> None:
        """Test removing a non-existent subscriber."""
        respx.delete(
            f"{API_BASE}{Endpoint.STATUSPAGES}/sp_1/subscribers/sub_nope"
        ).mock(return_value=httpx.Response(404, json={"error": "Not found"}))
        with pytest.raises(HyperpingNotFoundError):
            client.remove_subscriber("sp_1", "sub_nope")
