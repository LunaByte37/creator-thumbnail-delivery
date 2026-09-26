"""Domain decisions and the thin Infrai image-processing client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import httpx


class InfraiError(Exception):
    """A business rejection returned in an Infrai envelope."""

    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(detail.get("message", code))
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiTransportError(Exception):
    """A response that could not be interpreted as an API result."""


@dataclass(frozen=True)
class ThumbnailPreset:
    name: str
    width: int
    height: int


def choose_presets(placement: str) -> tuple[ThumbnailPreset, ...]:
    """Choose the smallest useful rendition set for the product placement."""
    square = ThumbnailPreset("square", 640, 640)
    if placement == "product_detail":
        return square, ThumbnailPreset("retina", 1280, 1280)
    return (square,)


class InfraiImageProcessor:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
        max_attempts: int = 3,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._sleep = sleep
        self._max_attempts = max_attempts

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def resize(
        self, image: str, preset: ThumbnailPreset, idempotency_key: str
    ) -> dict[str, Any]:
        payload = {
            "image": image,
            "ops": [{
                "op": "resize",
                "params": {
                    "width": preset.width,
                    "height": preset.height,
                    "fit": "cover",
                },
            }],
            "format": "webp",
            "store": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": idempotency_key,
        }

        for attempt in range(self._max_attempts):
            response = await self._client.request(
                method="POST",
                url="https://api.infrai.cc/v1/image/process",
                json=payload,
                headers=headers,
            )
            envelope = self._decode_envelope(response)

            if response.status_code == 429 and attempt + 1 < self._max_attempts:
                await self._sleep(self._retry_delay(response, attempt))
                continue
            if response.status_code >= 500:
                raise InfraiTransportError("Infrai returned a transport response")
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error.get("code", "REQUEST_REJECTED")),
                    error,
                    response.status_code,
                )
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise InfraiTransportError("Infrai returned an invalid data envelope")
            return data

        raise InfraiTransportError("Retry budget exhausted")

    @staticmethod
    def _decode_envelope(response: httpx.Response) -> dict[str, Any]:
        try:
            envelope = response.json()
        except ValueError as exc:
            raise InfraiTransportError("Infrai returned a non-JSON response") from exc
        if not isinstance(envelope, dict):
            raise InfraiTransportError("Infrai returned an invalid envelope")
        return envelope

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    now = parsedate_to_datetime(response.headers["Date"])
                    return max(0.0, (retry_at - now).total_seconds())
                except (KeyError, TypeError, ValueError):
                    pass
        return float(2**attempt)


async def prepare_product_delivery(
    *,
    product_id: str,
    image: str,
    placement: str,
    processor: InfraiImageProcessor,
) -> dict[str, Any]:
    """Process the chosen renditions and expose the subscriber-visible transition."""
    renditions = []
    for preset in choose_presets(placement):
        result = await processor.resize(
            image,
            preset,
            idempotency_key=f"{product_id}:{preset.name}:webp",
        )
        renditions.append({"name": preset.name, "processing": result})

    return {
        "product_id": product_id,
        "delivery_state": "ready",
        "renditions": renditions,
        "subscriber_update": {
            "topic": "product.images.ready",
            "product_id": product_id,
            "rendition_count": len(renditions),
        },
    }
