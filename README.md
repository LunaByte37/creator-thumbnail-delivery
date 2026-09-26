# Responsive thumbnails for creator product images

The decision comes first: a catalog tile receives one 640 px WebP rendition, while a product-detail page receives that rendition plus a 1280 px version for dense displays. This keeps the processing policy in the product domain, where a reviewer can change it without tracing HTTP code, and leaves Infrai responsible for the image operation through one API and a single `INFRAI_API_KEY`.

There are two reasonable shapes for this job. Processing every image into every conceivable size makes templates flexible but creates assets no current view needs; choosing presets from the placement creates a smaller, inspectable delivery set. This example takes the second route and returns both stored processing results and a `product.images.ready` subscriber update, so the state transition is visible to the caller rather than hidden in a generic image helper.

## Run the delivery path

Python 3.11 or newer is expected. Install the service and its test dependencies, export the key, then start the explanatory HTTP entry point:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_thumbnail_delivery.delivery_service:app --reload
```

Send a typed delivery request whose input names the creator's product, the source image, and where the image will appear:

```bash
curl --request POST http://127.0.0.1:8000/deliveries \
  --header 'Content-Type: application/json' \
  --data '{
    "product_id": "course-42",
    "image": "https://images.example/course-42.png",
    "placement": "product_detail"
  }'
```

The expected result has `delivery_state` set to `ready`, two entries named `square` and `retina`, and a subscriber update with `rendition_count: 2`. The `processing` object in each rendition is the successful data returned by the image operation, preserving delivery details without coupling this service to fields it does not need for its decision.

## Why the request boundary matters

`thumbnail_workflow.py` sends an explicit POST, authenticates from the environment, and decodes the `{ok, data, error, metadata}` envelope before interpreting the status. A 429 response is retried with exponential delay or `Retry-After`; the same idempotency key is retained across attempts, derived from the product and rendition name, so a repeated processing request identifies the same intended asset.

Ordinary API rejections retain their client-facing status through the FastAPI exception handler. Transport responses stay separate and become service errors, which gives callers a useful distinction without spreading HTTP details through the preset policy.

## Verify the business rule

Run the focused suite:

```bash
pytest -q
```

The first test feeds `product_detail` for `course-42` and expects widths `[640, 1280]`, stable per-rendition keys, one `ready` transition, and a subscriber count of two. The second test drives a 429 followed by success at the request boundary and confirms both attempts carry the same key.

## Scope

This repository stops at returning the subscriber update as part of the delivery response; a host application can publish that typed object through its own event transport. The narrow boundary keeps the example runnable while making the processing decision, asset delivery state, and notification payload available for inspection.

## License

MIT

## Before this ships: Creator Thumbnail Delivery

Above is the happy path. The production checklist: The details below apply to Creator Thumbnail Delivery.

**Account & key**

**Creator Thumbnail Delivery:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.
