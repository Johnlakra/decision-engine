# 0011 — One niche validator on the server; the browser checks YAML syntax only

**Status:** accepted · 2026-10-14 · Requirements: FR-70, FR-72, NFR-10 · Plan: phase 3 D6, steps 3.5-B1, 3.5b

## Context
- The Niches detail screen (3.5b) has a form and an "Advanced: YAML" editor. Users need to see errors where they typed.
- The server validator is `niches/loader.validate_niche_data` (jsonschema Draft 2020-12 over `schemas/niche.schema.json`,
  then Pydantic `NicheConfig`). It reports the **first** error as `{file, json_pointer, message}`.
- ADR 0009 adds semantic checks that only the server can run: registered actions and tools, `auto_actions ⊆ actions`,
  no `steps`, `generic` stays enabled, and the safety floor from the shipped YAML.
- PUT is all-or-nothing (ADR 0009): an invalid body writes nothing, so a failed save has no side effect.
- Server YAML is PyYAML `safe_load` (YAML 1.1: `yes/no/on/off` are booleans). The npm `yaml` package (2.9.1, ISC,
  no runtime dependencies; [registry](https://registry.npmjs.org/yaml/latest), checked 2026-10-14) defaults to YAML 1.2,
  where those are strings.

## Options considered
| | (a) Browser: YAML syntax only. Server: schema + semantic checks via `PUT` → `422` | (b) (a) + `POST /v1/niches/{name}/validate` dry run | (c) Ship the JSON Schema to the browser (Ajv) and validate there too |
|---|---|---|---|
| Drift | One validator | One validator, two routes | Two validators: Ajv vs Python `jsonschema` differ on formats/`$ref`, and semantic checks still need the server, so users see two kinds of error |
| UX | Syntax errors live as they type. Schema errors on Save, mapped to fields by `json_pointer` | Errors before Save | Live schema errors |
| Cost / ops | 0 extra routes; the bundle grows by the `yaml` package only | One more admin route, proxy rule, SDK op and tests, with no gain because PUT already has no side effect on failure | Ajv (~120 kB) + a schema copy kept in sync |

## Decision
**(a).** No validate endpoint, and no copy of the schema in the browser.

Browser (3.5b):
1. The YAML editor parses with `yaml` `parse(text, { version: "1.1", uniqueKeys: true, maxAliasCount: 50 })`, debounced
   300 ms. YAML 1.1 matches PyYAML, so the text means the same thing on both sides. A syntax error shows the line and
   column, and disables Save. The top level must be a mapping.
2. Save sends the parsed object as JSON to `PUT /v1/niches/{name}` (ADR 0009). The form fields and the YAML editor
   edit the same object.
3. A `422` maps each `errors[].json_pointer` to a form field when one exists (for example `/autonomy`). Otherwise it
   lists the pointer and message above the YAML editor. Pointer `""` means the whole document.

Server (3.5-B1), the error contract for `PUT /v1/niches/{name}`:
- `422` problem+json `{type: "about:blank", title: "Niche validation failed", status: 422, detail, errors:
  [{json_pointer, message}]}`. There is no `file` key (it is not a file). `/reload` keeps its `file` key.
- **All** schema errors, sorted by `json_pointer`, max 20. The first one equals what `validate_niche_data` reports
  today. Add an `all_errors=True` path to the loader and keep its current single-error behaviour for file loads.
- The ADR 0009 semantic checks run only when the schema passes (they assume valid types), with the same error shape.
- A body that is not a JSON object → one error with `json_pointer: ""`.

Example:
```json
// PUT /v1/niches/inbox   {..., "autonomy": "yolo", "auto_actions": ["send_reply"]}
// 422
{"type":"about:blank","title":"Niche validation failed","status":422,"detail":"1 problem; nothing was saved",
 "errors":[{"json_pointer":"/autonomy","message":"'yolo' is not one of ['suggest', 'ask', 'auto']"}]}
```

## Consequences
- Schema errors appear only on Save. Acceptable for an admin screen used rarely.
- One source of truth: `schemas/niche.schema.json`, read by Python. Schema changes need no web release.
- Acceptance 5 of the plan (`/autonomy` pointer on `yolo`) holds as written.

## Revisit when
- The FR-72 wizard (8.4) needs live validation while drafting. A dry run then comes with `POST /v1/niches/draft`
  anyway.

## Migration steps
1. backend-builder (3.5-B1): loader `all_errors` path, PUT error mapping, tests (multiple errors sorted, cap 20,
   non-object body, semantic checks skipped when the schema fails).
2. frontend-builder (3.5b): editor parse options and pointer-to-field mapping, with Vitest cases (`yes` parses as
   `true`, duplicate key is an error, pointer mapping).
3. Rollback: n/a (no new surface).
