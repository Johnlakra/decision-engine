---
description: Add a new source connector following docs/CONNECTORS.md (protocol, fixtures, signatures, docs).
argument-hint: <connector name, e.g. whatsapp>
---
Add the **$ARGUMENTS** connector.
1. Call `architect` if it needs a new dependency, OAuth app or changes the Connector protocol (ADR first).
2. Call `connector-builder`: read the provider's current API docs, implement poll/handle_webhook/map, signature
   verification, cursors, default sensitivity, source config schema, recorded fixtures and tests, docs row in
   docs/CONNECTORS.md. Platform rules (rate limits, messaging windows, account types) are requirements.
3. Call `security-auditor` on the diff (auth, secrets, signatures, SSRF, prompt injection fixtures).
4. Call `code-reviewer`, fix BLOCKING items, run `make test`, commit, `docs-keeper`.
Report what the owner must configure manually (developer app, keys, webhook URL).
