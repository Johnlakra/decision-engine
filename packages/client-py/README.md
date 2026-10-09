# decision-engine-client

Python client for the Decision Engine `/v1` API. `_generated/` is produced by `openapi-python-client`
(do not edit); `DecisionEngine` adds bearer auth, timeouts and retries (429 honouring `Retry-After`, 5xx,
connection errors).

```python
from decision_engine_client import DecisionEngine
from decision_engine_client._generated.models import IngestItemIn, IngestItemInPayloadType0

de = DecisionEngine("https://de.example.com", "<DE_API_KEY>", timeout=10, retries=3)
payload = IngestItemInPayloadType0.from_dict({"title": "Hello"})
result = de.create_item(IngestItemIn(source="radar", source_ref="story-42", payload=payload))
print(result.id)
```

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
