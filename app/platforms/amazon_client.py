from typing import Any

from creatorsapi_python_sdk.api.default_api import DefaultApi
from creatorsapi_python_sdk.api_client import ApiClient
from creatorsapi_python_sdk.models.get_items_request_content import (
    GetItemsRequestContent,
)
from creatorsapi_python_sdk.models.get_items_resource import (
    GetItemsResource,
)
from creatorsapi_python_sdk.models.search_items_request_content import (
    SearchItemsRequestContent,
)
from creatorsapi_python_sdk.models.search_items_resource import (
    SearchItemsResource,
)


class AmazonApiClient:
    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        partner_tag: str | None = None,
        marketplace: str = "www.amazon.com",
        credential_version: str | None = None,
        auth_endpoint: str | None = None,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.partner_tag = partner_tag
        self.marketplace = marketplace
        self.credential_version = credential_version
        self.auth_endpoint = auth_endpoint

        self._api_client: ApiClient | None = None
        self._api: DefaultApi | None = None

    def _get_api(self) -> DefaultApi | None:
        if not all(
            [
                self.access_key,
                self.secret_key,
                self.partner_tag,
                self.credential_version,
            ]
        ):
            return None

        if self._api is None:
            self._api_client = ApiClient(
                credential_id=self.access_key,
                credential_secret=self.secret_key,
                version=self.credential_version,
                host="https://creatorsapi.amazon",
                auth_endpoint=self.auth_endpoint,
            )

            self._api = DefaultApi(
                self._api_client
            )

        return self._api

    @staticmethod
    def _to_dict(
        response: Any,
    ) -> dict[str, Any] | None:
        if response is None:
            return None

        if hasattr(response, "to_dict"):
            return response.to_dict()

        if isinstance(response, dict):
            return response

        return None

    def get_items(
        self,
        asin: str,
    ) -> dict[str, Any] | None:
        api = self._get_api()

        if api is None:
            return None

        request = GetItemsRequestContent(
            partnerTag=self.partner_tag,
            itemIds=[asin],
            resources=[
                GetItemsResource.ITEM_INFO_DOT_TITLE,
                GetItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_PRICE,
                GetItemsResource.IMAGES_DOT_PRIMARY_DOT_LARGE,
            ],
        )

        response = api.get_items(
            x_marketplace=self.marketplace,
            get_items_request_content=request,
        )

        return self._to_dict(response)

    def search_items(
        self,
        keywords: str,
        search_index: str = "All",
        item_count: int = 10,
        item_page: int = 1,
        min_saving_percent: float | None = None,
    ) -> dict[str, Any] | None:
        api = self._get_api()

        if api is None:
            return None

        request = SearchItemsRequestContent(
            partnerTag=self.partner_tag,
            keywords=keywords,
            searchIndex=search_index,
            itemCount=item_count,
            itemPage=item_page,
            minSavingPercent=min_saving_percent,
            resources=[
                SearchItemsResource.ITEM_INFO_DOT_TITLE,
                SearchItemsResource.OFFERS_V2_DOT_LISTINGS_DOT_PRICE,
                SearchItemsResource.CUSTOMER_REVIEWS_DOT_STAR_RATING,
                SearchItemsResource.CUSTOMER_REVIEWS_DOT_COUNT,
                SearchItemsResource.IMAGES_DOT_PRIMARY_DOT_LARGE,
            ],
        )

        response = api.search_items(
            x_marketplace=self.marketplace,
            search_items_request_content=request,
        )

        return self._to_dict(response)

    def get_item(
        self,
        asin: str,
    ) -> dict[str, Any] | None:
        if not all(
            [
                self.access_key,
                self.secret_key,
                self.partner_tag,
                self.credential_version,
            ]
        ):
            raise NotImplementedError(
                "Amazon Creators API credentials are not configured."
            )

        return self.get_items(asin)
