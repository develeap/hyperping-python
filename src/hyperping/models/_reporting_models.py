"""Reporting models: status summary, response time, MTTA, MTTR."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StatusSummary(BaseModel):
    """Aggregate monitor status counts from get_status_summary."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    total: int = Field(default=0, description="Total monitor count")
    up: int = Field(default=0, description="Monitors currently up")
    down: int = Field(default=0, description="Monitors currently down")
    paused: int = Field(default=0, description="Monitors currently paused")
    unknown: int = Field(default=0, description="Monitors in unknown state")
    down_monitors: list[dict[str, Any]] = Field(
        default_factory=list, alias="down_monitors", description="Details of down monitors"
    )
    paused_monitors: list[dict[str, Any]] = Field(
        default_factory=list, alias="paused_monitors", description="Details of paused monitors"
    )


class TimeGroup(BaseModel):
    """Single time bucket in a time-series report."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    time: str = Field(..., description="Time bucket label (date string)")
    count: int = Field(default=0, description="Number of data points")
    avg_response_time: int | None = Field(
        default=None, alias="avgResponseTime", description="Average response time in ms"
    )


class ResponseTimeReport(BaseModel):
    """Response time report from get_monitor_response_time."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    time_groups: list[TimeGroup] = Field(
        default_factory=list, alias="timeGroups", description="Time-bucketed response data"
    )


class AlertHistory(BaseModel):
    """Alert notification history from list_recent_alerts."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    time_groups: list[TimeGroup] = Field(
        default_factory=list, alias="timeGroups", description="Time-bucketed alert counts"
    )


class MonitorMetricsSummary(BaseModel):
    """Per-monitor metrics entry in MTTA/MTTR reports."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Monitor UUID")
    name: str = Field(default="", description="Monitor name")
    protocol: str = Field(default="", description="Monitor protocol")
    outage_count: int = Field(default=0, alias="outageCount")
    total_downtime: int = Field(default=0, alias="totalDowntime", description="Seconds")
    mttr: int = Field(default=0, description="Mean time to resolve in seconds")
    mtta: int = Field(default=0, description="Mean time to acknowledge in seconds")
    longest_outage: int = Field(default=0, alias="longestOutage", description="Seconds")


class MttrReport(BaseModel):
    """MTTR report from get_monitor_mttr."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    monitors: list[MonitorMetricsSummary] = Field(default_factory=list)
    total_outages: int = Field(default=0, alias="totalOutages")
    total_outages_length: int = Field(default=0, alias="totalOutagesLength", description="Seconds")
    mttr: int = Field(default=0, description="Aggregate MTTR in seconds")
    mtta: int = Field(default=0, description="Aggregate MTTA in seconds")


class MttaReport(BaseModel):
    """MTTA report from get_monitor_mtta."""

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    monitors: list[MonitorMetricsSummary] = Field(default_factory=list)
    total_acknowledged: int = Field(default=0, alias="totalAcknowledged")
    mtta: int = Field(default=0, description="Aggregate MTTA in seconds")
