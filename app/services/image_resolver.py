import logging
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class _ImageMetaParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image_url = ""

    def handle_starttag(self, tag, attrs):
        if self.image_url:
            return

        attributes = dict(attrs)

        if tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or ""
            ).lower()

            if key in {
                "og:image",
                "og:image:url",
                "twitter:image",
                "twitter:image:src",
            }:
                self.image_url = (
                    attributes.get("content")
                    or ""
                ).strip()

        elif tag == "link":
            rel = (
                attributes.get("rel")
                or ""
            ).lower()

            if "image_src" in rel:
                self.image_url = (
                    attributes.get("href")
                    or ""
                ).strip()


class ImageResolver:
    def __init__(
        self,
        timeout: float = 10.0,
        get=requests.get,
    ):
        self.timeout = timeout
        self.get = get

    def _get_html(self, url: str) -> tuple[str, str]:
        response = self.get(
            url,
            timeout=self.timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/151 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,image/avif,"
                    "image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

        response.raise_for_status()

        return (
            response.text,
            response.url or url,
        )

    def _parse_meta_image(
        self,
        html: str,
        base_url: str,
    ) -> str:
        parser = _ImageMetaParser()
        parser.feed(html)

        if parser.image_url:
            return urljoin(
                base_url,
                parser.image_url,
            )

        return ""

    def _parse_amazon_image(
        self,
        html: str,
    ) -> str:
        patterns = [
            r'"landingImageUrl"\s*:\s*"([^"]+)"',
            r'"landingImage"\s*:\s*"([^"]+)"',
            r'"hiRes"\s*:\s*"([^"]+)"',
            r'"large"\s*:\s*"([^"]+)"',
            r'"mainImageUrl"\s*:\s*"([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                html,
                flags=re.IGNORECASE,
            )

            if not match:
                continue

            image_url = match.group(1)

            image_url = (
                image_url
                .replace("\\u002F", "/")
                .replace("\\/", "/")
                .replace("\\\"", '"')
            )

            if image_url.startswith("http"):
                return image_url

        return ""

    def resolve(
        self,
        source_url: str,
        fallback_urls: list[str] | None = None,
    ) -> str:
        urls = [source_url]

        if fallback_urls:
            urls.extend(
                url
                for url in fallback_urls
                if url and url not in urls
            )

        for url in urls:
            try:
                html, final_url = self._get_html(url)

                image_url = self._parse_meta_image(
                    html,
                    final_url,
                )

                if image_url:
                    return image_url

                if "amazon." in final_url.lower():
                    image_url = (
                        self._parse_amazon_image(
                            html
                        )
                    )

                    if image_url:
                        return image_url

            except requests.RequestException:
                continue
            except Exception as exc:
                logger.warning(
                    "image candidate failed for %s: %s",
                    url,
                    exc,
                )
                continue

        return ""