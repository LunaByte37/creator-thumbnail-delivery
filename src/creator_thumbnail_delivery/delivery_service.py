"""HTTP entry point for creator product thumbnail delivery."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .thumbnail_workflow import InfraiError, InfraiImageProcessor, prepare_product_delivery


class ProductImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=120)
    image: HttpUrl
    placement: Literal["catalog", "product_detail"]


class SubscriberUpdate(BaseModel):
    topic: Literal["product.images.ready"]
    product_id: str
    rendition_count: int


class ProductDeliveryResponse(BaseModel):
    product_id: str
    delivery_state: Literal["ready"]
    renditions: list[dict[str, object]]
    subscriber_update: SubscriberUpdate


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    app.state.processor = InfraiImageProcessor(api_key)
    yield
    await app.state.processor.close()


app = FastAPI(title="Creator Thumbnail Delivery", lifespan=lifespan)


@app.exception_handler(InfraiError)
async def handle_infrai_error(_: Request, exc: InfraiError) -> JSONResponse:
    status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


@app.post("/deliveries", response_model=ProductDeliveryResponse)
async def create_delivery(payload: ProductImageRequest, request: Request) -> dict[str, object]:
    return await prepare_product_delivery(
        product_id=payload.product_id,
        image=str(payload.image),
        placement=payload.placement,
        processor=request.app.state.processor,
    )

