from typing import Any


class AmazonApiClient:
    """
    Low-level client for Amazon Creators API.

    Authentication and HTTP communication are isolated here so the
    AmazonProvider does not need to know how the API works.
    """

    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        partner_tag: str | None = None,
        marketplace: str = "www.amazon.com",
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.marketplace = marketplace

    def get_item(self, asin: str) -> dict[str, Any] | None:
        """
        Retrieve one Amazon item by ASIN.

        HTTP/OAuth implementation will be added in the next stage.
        """
        raise NotImplementedError(
            "Amazon Creators API HTTP integration will be implemented next."
        )
