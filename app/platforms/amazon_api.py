from dataclasses import dataclass
from typing import Any
import time

import requests


@dataclass
class AmazonApiClient:
    credential_id: str
    credential_secret: str
    credential_version: str
    partner_tag: str
    marketplace: str = "www.amazon.com"

    BASE_URL = "https://creatorsapi.amazon"
    TOKEN_URL = "https://api.amazon.com/auth/o2/token"

    def __post_init__(self):
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    def build_get_items_request(self, asin: str) -> dict[str, Any]:
        return {
            "itemIds": [asin],
            "itemIdType": "ASIN",
            "marketplace": self.marketplace,
            "partnerTag": self.partner_tag,
            "resources": [
                "itemInfo.title",
                "offersV2.listings.price",
                "images.primary.large",
            ],
        }

    def build_get_items_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-amz-access-token": access_token,
            "x-amz-date": "20260815T000000Z",
        }

    def build_get_items_url(self) -> str:
        return f"{self.BASE_URL}/paapi5/getitems"

    def get_items(self, asin: str) -> dict[str, Any]:
        access_token = self.get_access_token()

        response = requests.post(
            self.build_get_items_url(),
            headers=self.build_get_items_headers(access_token),
            json=self.build_get_items_request(asin),
            timeout=15,
        )

        response.raise_for_status()

        return response.json()

    def get_access_token(self) -> str:
        now = time.time()

        if (
            self._access_token is not None
            and now < self._token_expires_at
        ):
            return self._access_token

        response = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.credential_id,
                "client_secret": self.credential_secret,
                "version": self.credential_version,
                "scope": "creatorsapi::default",
            },
            timeout=15,
        )

        response.raise_for_status()

        payload = response.json()

        self._access_token = payload["access_token"]

        expires_in = int(
            payload.get("expires_in", 3600)
        )

        # Pequena margem para evitar usar token no limite da expiração.
        self._token_expires_at = (
            now + max(expires_in - 60, 1)
        )

        return self._access_token
