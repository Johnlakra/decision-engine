# decision-engine-client

Python client for the Decision Engine `/v1` API. `_generated/` is produced by `openapi-python-client`
(do not edit); `DecisionEngine` adds bearer auth, timeouts and retries.

```python
from decision_engine_client import DecisionEngine
from decision_engine_client._generated.models import IngestItemIn, IngestItemInPayloadType0

de = DecisionEngine("https://de.example.com", "<DE_API_KEY>", timeout=10, retries=3)
payload = IngestItemInPayloadType0.from_dict({"title": "Hello"})
result = de.create_item(IngestItemIn(source="radar", source_ref="story-42", payload=payload))
print(result.id)
```

## Retry policy

Retries use a method plus path allow-list (backoff 0.5 s doubling, `Retry-After` honoured):

| Call | Retried on |
|---|---|
| `GET` anything | 429, 5xx, connect error, read timeout, protocol error |
| `POST /v1/items`, `POST /v1/items/bulk` | same (ingest is idempotent on `source`+`source_ref`) |
| `POST /v1/decide` | only 429 with `Retry-After`; never on 5xx or timeout (503 `no-private-provider` is permanent) |
| `POST /v1/items/{id}/decision` | only 429 with `Retry-After` |
| everything else (subscriptions, ...) | only 429 with `Retry-After` |

`decide()` uses a timeout of `max(timeout, 35)` seconds because the server budget is 30 s.

`de.raw` is the full generated `AuthenticatedClient` for any other endpoint.

## Verify a webhook

```python
from decision_engine_client import InvalidSignature, verify_signature

try:
    verify_signature(secret_bytes, raw_body_bytes, request.headers["X-DE-Signature"])
except InvalidSignature as exc:
    reject(exc.reason)
```

Install from the repo: `uv add "decision-engine-client @ git+https://<repo>#subdirectory=packages/client-py"`.
Regenerate with `make sdk`.
