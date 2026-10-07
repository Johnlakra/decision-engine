# Connectors

A connector turns an outside source into `IngestItem`s (pull: `poll()` from the worker scheduler; push:
`handle_webhook()`), and maps raw payloads to normalised content without an LLM where possible (`map()`).
Every connector: idempotent `source_ref`, cursor stored in `sources.cursor`, error count + backoff, health
shown in UI, tests with recorded fixtures (`tests/fixtures/<connector>/`), never logs bodies.

| Connector | Phase | Mode | Default sensitivity | Notes |
|---|---|---|---|---|
| `rss` (RSS/Atom, Google News query, HN Algolia) | 2 | poll 15 min | public | conditional GET (ETag/Last-Modified); `feedparser`; Google News URL `https://news.google.com/rss/search?q=<q>&hl=en-IN&gl=IN&ceid=IN:en` |
| `telegram` | 2 | push (webhook) or long-poll | private | input: forwards/texts/voice → items; notifier + inline buttons `de:a:<id>` approve, `de:r:<id>` reject; verify `X-Telegram-Bot-Api-Secret-Token`; only allow-listed chat ids |
| `radar` (Opportunity Radar) | 2 | push (`POST /v1/items` with `source=radar`) | public | `hints.niche=news_radar`, pass radar score/category in payload |
| `gmail` | 4 | poll `users.history.list` every 5 min (Pub/Sub push SHOULD) | private | see below |
| `instagram` | 5 | push (Meta webhook `messages`) | private | see below |
| `webhook` (generic) | 5 | push `POST /v1/webhooks/{slug}` | per source | HMAC `t=…,v1=…`, 5-min skew, replay cache of (t, sig) 10 min |
| `csv` / uploads | 5 | upload job | per upload | mapping UI; ≤ 20 MB; streaming parse |
| `voice` | 7 | via telegram/mobile upload | private | Sarvam STT → text; keep audio ref, delete audio after `AUDIO_RETENTION_DAYS` (7) |
| `whatsapp`, `outlook`, `slack`, `calendar` | later | — | — | WhatsApp Cloud API needs a business number and template rules |

## Gmail
- OAuth 2.0 web flow; scopes start with `gmail.readonly`; add `gmail.modify` (labels/archive) and `gmail.compose`
  (drafts) only when those actions are enabled. These are **restricted scopes**: keep the Google Cloud app in
  **Testing** with the owner as test user (refresh tokens for Testing apps expire after 7 days — the UI must show
  "reconnect" when refresh fails). Public launch requires Google verification + CASA assessment (budget it).
- Store refresh token encrypted (`TOKEN_ENC_KEY`, Fernet). Never request `mail.google.com` full scope.
- First sync: last 7 days, `in:inbox -category:promotions` optional filter; then `history.list(startHistoryId)`.
- Map: subject→title, snippet/plain body (HTML→text, quoted replies stripped)→body, From→sender, `Message-Id`→source_ref,
  `https://mail.google.com/mail/u/0/#inbox/<threadId>`→url, attachments metadata only (download on demand, FR-05).
- Actions: `gmail.label`, `gmail.archive` (remove INBOX), `gmail.create_draft` (threaded reply). **No send** in MVP.

## Instagram (Meta)
- Only **professional (Business/Creator)** accounts, via Instagram API with Instagram Login
  (`instagram_business_basic`, `instagram_business_manage_messages`). Personal accounts: not possible — say so in UI.
- Webhook verify (`hub.challenge`) + `X-Hub-Signature-256` HMAC with the app secret.
- Replies only within **24 h** of the user's last message (human agent tag allows 7 days for human-typed replies);
  no cold outreach; no scraping or unofficial APIs. Our action creates a **draft** shown in the queue; sending is an
  approved action that checks the window first.
- Serving accounts other than the owner's needs Meta App Review + business verification (LATER).

## Generic webhook
`POST /v1/webhooks/{slug}`; body any JSON; signature over raw bytes; mapping per source (JSONPath for title/body/
sender/url/source_ref) configured in the Sources UI; fallback to LLM normaliser.

## Adding a connector (`/new-connector <name>`)
1. ADR if it needs a new dependency or OAuth app. 2. `connectors/<name>.py` implementing the protocol.
3. Fixtures + unit tests for `map()`, integration test for poll/webhook with respx. 4. Source config schema in
`schemas/sources/<name>.json`. 5. Docs row above. 6. Security-auditor review for auth/secret handling.
