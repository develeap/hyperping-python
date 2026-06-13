"""Async streaming helpers for event-driven integrations (PY-10).

Provides poll-based AsyncIterator helpers on top of existing REST endpoints.
Public signatures are stable; only the poll internals change when Hyperping
ships SSE or a discrete alerts endpoint.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from hyperping._protocols import _AsyncClientProtocol
from hyperping._utils import parse_list, unwrap_list, validate_id
from hyperping.endpoints import Endpoint
from hyperping.models import IncidentUpdate, Monitor
from hyperping.models._alert_models import Alert, AlertType

if TYPE_CHECKING:
    from hyperping.models import Incident

logger = logging.getLogger(__name__)


class AsyncStreamingMixin(_AsyncClientProtocol):
    """Poll-based streaming helpers for alert and incident monitoring."""

    if TYPE_CHECKING:

        async def get_incident(self, incident_id: str) -> Incident: ...

    async def stream_alerts(self, *, poll_interval: float = 30.0) -> AsyncIterator[Alert]:
        """Stream monitor state-transition events.

        Polls ``GET /v1/monitors`` at *poll_interval* seconds. Yields an
        :class:`~hyperping.models.Alert` on each up/down state change.
        The first poll establishes the baseline and yields nothing.

        Rate-limit note: at the default 30-second interval this uses
        2 requests/min, roughly 0.67% of the 300 req/min account limit.

        Args:
            poll_interval: Seconds between polls. Defaults to 30.0.

        Yields:
            :class:`~hyperping.models.Alert` on each monitor state transition.

        Note:
            This implementation is provisional. The ``Alert`` model fields are
            inferred from the monitors list endpoint. When Hyperping ships a
            dedicated alerts endpoint, the model will be reconciled and the
            poll internals replaced with SSE or long-poll without any change
            to this method's signature.
        """
        baseline: dict[str, bool] = {}

        while True:
            response = await self._request("GET", Endpoint.MONITORS)
            monitors = parse_list(unwrap_list(response, "monitors"), Monitor, "monitor")

            for monitor in monitors:
                uuid = monitor.uuid
                down = monitor.down

                if uuid in baseline and baseline[uuid] != down:
                    alert_type = AlertType.DOWN if down else AlertType.UP
                    yield Alert(
                        monitor_uuid=uuid,
                        monitor_name=monitor.name,
                        type=alert_type,
                        timestamp=datetime.now(UTC).isoformat(),
                    )

                baseline[uuid] = down

            await asyncio.sleep(poll_interval)

    async def stream_incident_updates(
        self, incident_uuid: str, *, poll_interval: float = 30.0
    ) -> AsyncIterator[IncidentUpdate]:
        """Stream new updates for an incident.

        Polls ``GET /v3/incidents/{uuid}`` at *poll_interval* seconds. Yields
        each :class:`~hyperping.models.IncidentUpdate` exactly once, deduped
        by update UUID. All updates present on the first poll are yielded
        immediately; only new updates are yielded on subsequent polls.

        Args:
            incident_uuid: UUID of the incident to watch.
            poll_interval: Seconds between polls. Defaults to 30.0.

        Yields:
            :class:`~hyperping.models.IncidentUpdate` for each new update.

        Raises:
            ValueError: If *incident_uuid* contains unsafe characters.
            HyperpingNotFoundError: If the incident does not exist (first poll).
        """
        validate_id(incident_uuid, "incident_uuid")
        seen: set[str] = set()

        while True:
            incident = await self.get_incident(incident_uuid)

            for update in incident.updates:
                if update.uuid not in seen:
                    seen.add(update.uuid)
                    yield update

            await asyncio.sleep(poll_interval)
