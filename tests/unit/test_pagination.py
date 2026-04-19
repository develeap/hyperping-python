"""Tests for pagination support on outages and statuspages endpoints."""

import httpx
import respx

from hyperping.client import HyperpingClient
from hyperping.endpoints import API_BASE, Endpoint


class TestOutagesPagination:
    """Tests for list_outages() pagination parameters."""

    @respx.mock
    def test_list_outages_single_page_explicit(self, client: HyperpingClient) -> None:
        """Explicit page=0 fetches only that page."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "outages": [{"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            )
        )
        outages = client.list_outages(page=0)
        assert len(outages) == 1
        assert outages[0].uuid == "out_1"
        # Only one request made (did not follow hasNextPage)
        assert respx.calls.call_count == 1

    @respx.mock
    def test_list_outages_auto_paginate_two_pages(self, client: HyperpingClient) -> None:
        """page=None auto-paginates until hasNextPage is False."""
        calls = [
            httpx.Response(
                200,
                json={
                    "outages": [{"uuid": "out_1", "monitor_uuid": "mon_1", "status": "active"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            ),
            httpx.Response(
                200,
                json={
                    "outages": [{"uuid": "out_2", "monitor_uuid": "mon_2", "status": "resolved"}],
                    "hasNextPage": False,
                    "total": 2,
                },
            ),
        ]
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(side_effect=calls)
        outages = client.list_outages()
        assert len(outages) == 2
        assert [o.uuid for o in outages] == ["out_1", "out_2"]
        assert respx.calls.call_count == 2

    @respx.mock
    def test_list_outages_filter_status(self, client: HyperpingClient) -> None:
        """status param is forwarded as a query parameter."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json={"outages": [], "hasNextPage": False, "total": 0})
        )
        client.list_outages(status="ongoing")
        request = respx.calls.last.request
        assert "status=ongoing" in str(request.url)

    @respx.mock
    def test_list_outages_filter_type(self, client: HyperpingClient) -> None:
        """outage_type param is forwarded as 'type' query parameter."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json={"outages": [], "hasNextPage": False, "total": 0})
        )
        client.list_outages(outage_type="monitor")
        request = respx.calls.last.request
        assert "type=monitor" in str(request.url)

    @respx.mock
    def test_list_outages_default_omits_all_filters(self, client: HyperpingClient) -> None:
        """Default call does not send status or type params."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(200, json={"outages": [], "hasNextPage": False, "total": 0})
        )
        client.list_outages()
        request = respx.calls.last.request
        assert "status=" not in str(request.url)
        assert "type=" not in str(request.url)

    @respx.mock
    def test_list_outages_404_returns_empty(self, client: HyperpingClient) -> None:
        """404 during pagination still returns empty list."""
        respx.get(f"{API_BASE}{Endpoint.OUTAGES}").mock(
            return_value=httpx.Response(404, json={"error": "Not found"})
        )
        assert client.list_outages() == []


class TestStatusPagesPagination:
    """Tests for list_status_pages() pagination parameters."""

    @respx.mock
    def test_list_status_pages_single_page_explicit(self, client: HyperpingClient) -> None:
        """Explicit page=0 fetches only that page."""
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "statuspages": [{"uuid": "sp_1", "name": "Page 1", "subdomain": "p1"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            )
        )
        pages = client.list_status_pages(page=0)
        assert len(pages) == 1
        assert respx.calls.call_count == 1

    @respx.mock
    def test_list_status_pages_auto_paginate(self, client: HyperpingClient) -> None:
        """page=None auto-paginates until hasNextPage is False."""
        calls = [
            httpx.Response(
                200,
                json={
                    "statuspages": [{"uuid": "sp_1", "name": "Page 1", "subdomain": "p1"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            ),
            httpx.Response(
                200,
                json={
                    "statuspages": [{"uuid": "sp_2", "name": "Page 2", "subdomain": "p2"}],
                    "hasNextPage": False,
                    "total": 2,
                },
            ),
        ]
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(side_effect=calls)
        pages = client.list_status_pages()
        assert len(pages) == 2
        assert respx.calls.call_count == 2

    @respx.mock
    def test_list_status_pages_search_param(self, client: HyperpingClient) -> None:
        """search param is forwarded as a query parameter."""
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}").mock(
            return_value=httpx.Response(
                200,
                json={"statuspages": [], "hasNextPage": False, "total": 0},
            )
        )
        client.list_status_pages(search="prod")
        request = respx.calls.last.request
        assert "search=prod" in str(request.url)


class TestSubscribersPagination:
    """Tests for list_subscribers() pagination parameters."""

    @respx.mock
    def test_list_subscribers_single_page_explicit(self, client: HyperpingClient) -> None:
        """Explicit page=0 fetches only that page."""
        sp_id = "sp_abc"
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/{sp_id}/subscribers").mock(
            return_value=httpx.Response(
                200,
                json={
                    "subscribers": [{"id": "sub_1", "email": "a@b.com"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            )
        )
        subs = client.list_subscribers(sp_id, page=0)
        assert len(subs) == 1
        assert respx.calls.call_count == 1

    @respx.mock
    def test_list_subscribers_auto_paginate(self, client: HyperpingClient) -> None:
        """page=None auto-paginates until hasNextPage is False."""
        sp_id = "sp_abc"
        calls = [
            httpx.Response(
                200,
                json={
                    "subscribers": [{"id": "sub_1", "email": "a@b.com"}],
                    "hasNextPage": True,
                    "total": 2,
                },
            ),
            httpx.Response(
                200,
                json={
                    "subscribers": [{"id": "sub_2", "email": "c@d.com"}],
                    "hasNextPage": False,
                    "total": 2,
                },
            ),
        ]
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/{sp_id}/subscribers").mock(side_effect=calls)
        subs = client.list_subscribers(sp_id)
        assert len(subs) == 2
        assert respx.calls.call_count == 2

    @respx.mock
    def test_list_subscribers_type_filter(self, client: HyperpingClient) -> None:
        """subscriber_type param is forwarded as 'type' query parameter."""
        sp_id = "sp_abc"
        respx.get(f"{API_BASE}{Endpoint.STATUSPAGES}/{sp_id}/subscribers").mock(
            return_value=httpx.Response(
                200,
                json={"subscribers": [], "hasNextPage": False, "total": 0},
            )
        )
        client.list_subscribers(sp_id, subscriber_type="email")
        request = respx.calls.last.request
        assert "type=email" in str(request.url)
