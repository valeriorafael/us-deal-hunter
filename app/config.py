import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.platforms.amazon_client import AmazonApiClient
from app.publication.telegram import TelegramPublisher


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
            access_key=self.credential_id,
            secret_key=self.credential_secret,
            credential_version=self.credential_version,
            partner_tag=self.partner_tag,
        )

    def build_client(self) -> AmazonApiClient:
        return self.create_client()


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_environment(cls) -> "TelegramConfig":
        load_dotenv()

        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        missing = []

        if not bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")

        if not chat_id:
            missing.append("TELEGRAM_CHAT_ID")

        if missing:
            raise ValueError(
                "Missing Telegram configuration: "
                + ", ".join(missing)
            )

        return cls(
            bot_token=bot_token,
            chat_id=chat_id,
        )

    def create_publisher(self) -> TelegramPublisher:
        return TelegramPublisher(
            bot_token=self.bot_token,
            chat_id=self.chat_id,
        )


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
        return all(
            os.getenv(name)
            for name in (
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_CHAT_ID",
            )
        )
