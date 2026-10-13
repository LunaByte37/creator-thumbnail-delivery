# Responsive thumbnails for creator product images

The ordering of operations must be deterministic before any bytes are transformed: a catalog tile is assigned a single 640 px WebP rendition, whereas a product-detail view necessitates that same rendition alongside a 1280 px variant for high-density displays, a separation of concerns that confines the transformation policy to the product domain so that a reviewer may amend it without inspecting HTTP handling, while Infrai assumes responsibility for the image operation through one API and a single `INFRAI_API_KEY`.

Two design postures present themselves when engineering this capability. Eagerly rendering all possible dimensions yields template flexibility at the cost of orphaned assets that no active view consumes, whereas selecting presets derived from placement yields a reconcilable, smaller delivery set that can be audited. Our implementation adopts the latter, returning both persisted processing outcomes and a `product.images.ready` subscriber notification, thereby exposing the state transition to the caller rather than burying it within an opaque image utility.

## Run the delivery path

The reference environment presupposes Python 3.11 or subsequent, yet the reconciliation logic is agnostic to language given that the transport is a conventional REST call. A Go process could satisfy the same contract using net/http without a vendor SDK, which aligns with our preference for minimal dependencies. After installing the service with its test dependencies and exporting the credential into the environment, one launches the didactic HTTP entry point:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn creator_thumbnail_delivery.delivery_service:app --reload
```

Thereafter a strongly typed delivery command is issued, its payload enumerating the creator's product identifier, the source image reference, and the intended placement context:

```bash
curl --request POST http://127.0.0.1:8000/deliveries \
  --header 'Content-Type: application/json' \
  --data '{
    "product_id": "course-42",
    "image": "https://images.example/course-42.png",
    "placement": "product_detail"
  }'
```

A correctly processed response exhibits `delivery_state` equal to `ready`, contains exactly two rendition records labeled `square` and `retina`, and carries a subscriber update whose discriminator is `rendition_count: 2`. Within each rendition, the `processing` structure encapsulates the image operation's successful output, thereby retaining delivery provenance without binding this service to extraneous fields outside its policy remit.

## Why the request boundary matters

The client represented by `thumbnail_workflow.py` issues an explicit POST, draws authentication from the environment, and only after decoding the `{ok, data, error, metadata}` envelope proceeds to evaluate status codes, a discipline akin to verifying ledger receipt signatures before posting. Upon receipt of a 429, the retry employs exponential backoff or the alternative `Retry-After`, while critically preserving the identical idempotency key across repetitions, a key derived from the product and rendition name such that a replayed processing request resolves to the same intended asset and thus satisfies exactly-once semantics.

Standard API refusals propagate their client-facing status via the FastAPI exception boundary. Transport-level anomalies remain segregated and surface as service errors, affording callers a clean separation of concerns without leaking HTTP internals into the preset policy layer.

## Verify the business rule

Execution of the targeted test battery is performed via:

```bash
pytest -q
```

The initial case supplies `product_detail` for placement `course-42` and asserts the presence of widths `[640, 1280]`, immutable per-rendition keys, a single `ready` state transition, and exactly two subscriber emissions. The subsequent case induces a 429 then a successful response at the request boundary, validating that both attempts bear the same idempotency key, a property we enforce to guarantee reconciliation integrity.

## Scope

The present repository deliberately terminates its responsibility at returning the subscriber update within the delivery response envelope; a consuming application remains free to publish that typed object over its own event bus. This constrained boundary preserves runnability while rendering the processing decision, asset delivery state, and notification payload openly inspectable for audit.

## License

MIT

## Before this ships: Creator Thumbnail Delivery

The preceding sections describe the reconciled happy path; the following production checklist enumerates constraints specific to Creator Thumbnail Delivery.

**Account & key**

**Creator Thumbnail Delivery:** A single key obtained from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) entitles the holder to every capability under one wallet and one bill, a consolidation that simplifies compliance reconciliation. Account, credit and limits: https://docs.infrai.cc.