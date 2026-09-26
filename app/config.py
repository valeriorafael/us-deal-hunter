import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.platforms.amazon_api import AmazonApiClient


@dataclass(frozen=True)
class AmazonConfig:
    credential_id: str
    credential_secret: str
    credential_version: str
    partner_tag: str

    @classmethod
    def from_environment(cls) -> "AmazonConfig":
        load_dotenv()

        required = {
            "AMAZON_CREDENTIAL_ID": os.getenv("AMAZON_CREDENTIAL_ID"),
            "AMAZON_CREDENTIAL_SECRET": os.getenv(
                "AMAZON_CREDENTIAL_SECRET"
            ),
            "AMAZON_CREDENTIAL_VERSION": os.getenv(
                "AMAZON_CREDENTIAL_VERSION"
            ),
            "AMAZON_PARTNER_TAG": os.getenv(
                "AMAZON_PARTNER_TAG"
            ),
        }

        missing = [
            name
            for name, value in required.items()
            if not value
        ]

        if missing:
            raise ValueError(
                "Missing Amazon credentials: "
                + ", ".join(missing)
            )

        return cls(
            credential_id=required["AMAZON_CREDENTIAL_ID"],
            credential_secret=required["AMAZON_CREDENTIAL_SECRET"],
            credential_version=required["AMAZON_CREDENTIAL_VERSION"],
            partner_tag=required["AMAZON_PARTNER_TAG"],
        )

    def create_client(self) -> AmazonApiClient:
        return AmazonApiClient(
            credential_id=self.credential_id,
            credential_secret=self.credential_secret,
            credential_version=self.credential_version,
            partner_tag=self.partner_tag,
        )

    def build_client(self) -> AmazonApiClient:
        return self.create_client()


@dataclass
class Settings:
    @property
    def amazon_configured(self) -> bool:
        return all(
            os.getenv(name)
            for name in (
                "AMAZON_CREDENTIAL_ID",
                "AMAZON_CREDENTIAL_SECRET",
                "AMAZON_CREDENTIAL_VERSION",
                "AMAZON_PARTNER_TAG",
            )
        )

    @property
    def telegram_configured(self) -> bool:
        return bool(os.getenv("TELEGRAM_BOT_TOKEN"))
