"""Status page models for Hyperping API v2."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StatusPage(BaseModel):
    """Model for a status page response from v2 API.

    API: GET /v2/statuspages, GET /v2/statuspages/{uuid}
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    uuid: str = Field(..., description="Status page UUID")
    name: str = Field(..., description="Status page display name")
    # The v2 list/get API returns the hosted subdomain under the key
    # ``hostedsubdomain`` and omits it entirely on some responses. It was
    # previously modelled as a required ``subdomain`` field, which made every
    # record fail validation and be silently dropped (list_status_pages
    # returned []). Alias to the real key and make it optional.
    subdomain: str | None = Field(
        default=None,
        alias="hostedsubdomain",
        description="Hosted status page subdomain (API key: 'hostedsubdomain'; may be absent)",
    )
    hostname: str | None = Field(default=None, description="Custom domain hostname, if any")
    url: str | None = Field(default=None, description="Public status page URL")
    custom_domain: str | None = Field(
        default=None, alias="customDomain", description="Custom domain"
    )
    public: bool = Field(default=True, description="Whether the page is publicly accessible")
    monitors: list[str] = Field(
        default_factory=list, description="Monitor UUIDs shown on this page"
    )


class StatusPageCreate(BaseModel):
    """Model for creating a new status page.

    API: POST /v2/statuspages
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=255, description="Status page display name")
    subdomain: str = Field(..., description="Status page subdomain")
    custom_domain: str | None = Field(
        default=None, alias="customDomain", description="Custom domain"
    )
    public: bool = Field(default=True, description="Whether the page is publicly accessible")
    monitors: list[str] = Field(
        default_factory=list, description="Monitor UUIDs shown on this page"
    )


class StatusPageUpdate(BaseModel):
    """Model for updating an existing status page (all fields optional).

    API: PUT /v2/statuspages/{uuid}
    """

    model_config = ConfigDict(use_enum_values=True, populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    subdomain: str | None = None
    custom_domain: str | None = Field(default=None, alias="customDomain")
    public: bool | None = None
    monitors: list[str] | None = None


class StatusPageSubscriber(BaseModel):
    """Model for a status page subscriber.

    API: GET /v2/statuspages/{uuid}/subscribers
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True, frozen=True)

    id: str = Field(..., description="Subscriber ID")
    email: str = Field(..., description="Subscriber email address")
