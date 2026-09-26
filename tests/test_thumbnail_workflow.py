from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from creator_thumbnail_delivery.thumbnail_workflow import (
    InfraiImageProcessor,
    ThumbnailPreset,
    prepare_product_delivery,
)


class RecordingProcessor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ThumbnailPreset, str]] = []

    async def resize(
        self, image: str, preset: ThumbnailPreset, idempotency_key: str
    ) -> dict[str, Any]:
        self.calls.append((image, preset, idempotency_key))
        return {"asset_id": f"stored-{preset.name}"}


@pytest.mark.asyncio
async def test_product_detail_gets_two_renditions_and_one_ready_update() -> None:
    processor = RecordingProcessor()

    result = await prepare_product_delivery(
        product_id="course-42",
        image="https://images.example/course-42.png",
        placement="product_detail",
        processor=processor,  # type: ignore[arg-type]
    )

    assert [call[1].width for call in processor.calls] == [640, 1280]
    assert [call[2] for call in processor.calls] == [
        "course-42:square:webp",
        "course-42:retina:webp",
    ]
    assert result["delivery_state"] == "ready"
    assert result["subscriber_update"] == {
        "topic": "product.images.ready",
        "product_id": "course-42",
        "rendition_count": 2,
    }


@pytest.mark.asyncio
async def test_retry_keeps_the_same_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"asset_id": "stored-square"}, "error": None, "metadata": {}},
        )

    async def no_sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        processor = InfraiImageProcessor(client=client, api_key="test-key", sleep=no_sleep)
        result = await processor.resize(
            "https://images.example/item.png",
            ThumbnailPreset("square", 640, 640),
            "item-7:square:webp",
        )

    assert result == {"asset_id": "stored-square"}
    assert len(seen) == 2
    assert {request.headers["Idempotency-Key"] for request in seen} == {"item-7:square:webp"}
    assert all(json.loads(request.content) == {
        "image": "https://images.example/item.png",
        "ops": [{"op": "resize", "params": {
            "width": 640, "height": 640, "fit": "cover",
        }}],
        "format": "webp",
        "store": True,
    } for request in seen)
