# Laya in this project

Laya (`convaiinnovations/laya`, Apache-2.0, `pip install "laya[serve]"`, verified version **0.3.27**) is an
encoder decision model: it answers typed questions about a text with probabilities in one forward pass and
never generates text. We use it for **triage and keep/skip only**. LLMs do extraction, reasoning and writing.

## 1. Service (`services/laya/`)
```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir "laya[serve]==0.3.27"
ENV LAYA_MODELS=english,multilingual LAYA_PRELOAD=1 LAYA_THREADS=2 LAYA_MAX_CONCURRENT=4 \
    LAYA_MAX_LOADED=2 HF_HOME=/models
EXPOSE 8000
CMD ["laya-serve"]
```
- RAM: plan 4 GB with both checkpoints (english 421M ≈ 0.8 GB download, multilingual 322M ≈ 0.65 GB).
  English-only items? set `LAYA_MODELS=english` to save RAM. Hindi/Punjabi/Hinglish need `multilingual`.
- Always set `LAYA_API_KEY` (server has no auth otherwise). Persist `/models` in a volume.
- Server limits (from `laya/serve.py`): ≤ 64 states per batch, ≤ 64 questions, ≤ 50,000 chars per state;
  over `LAYA_MAX_CONCURRENT` → `503` with `Retry-After: 1`.
- Auto-routing: with no `model` in the request the server's Router picks english/multilingual per state by
  script/language. Keep it that way.

## 2. Wire format
`POST {LAYA_URL}/v1/systemone/batch` · `Authorization: Bearer {LAYA_API_KEY}`
```json
{"states": ["Subject: Invoice overdue\nFrom: …\n…"],
 "questions": {
   "needs_decision": {"type": "choice", "instructions": "Does this require the owner to decide or act?",
                      "criteria": {"A": "yes, a decision or action is needed", "B": "no, informational only"}},
   "niche": {"type": "choice", "instructions": "Which area does this belong to?",
             "criteria": {"inbox": "<niche.description>", "news_radar": "<…>", "generic": "<…>"}},
   "urgency": {"type": "score", "instructions": "How soon must the owner act?",
               "criteria": ["can wait a week or more", "this week", "today or overdue"]},
   "risk": {"type": "choice", "instructions": "Is this a normal message, spam, or a scam/phishing attempt?",
            "criteria": {"normal": "a normal legitimate item", "spam": "unwanted bulk marketing",
                         "scam_or_phishing": "asks for passwords, OTP, money to strangers, or fakes a brand"}}}}
```
Response `{"results": [{"answers": {"<qid>": {...}}, "usage": {...}, "routing": {"model": "...", "reason": "..."}}], "total_usage": {...}}`
- `choice` → `{"type":"choice","choice":"A","probabilities":{"A":0.91,"B":0.09},"confidence":0.84,"answer_confidence":…}`
- `score` → `{"type":"score","score":1.6,"probabilities":{"0":…,"1":…,"2":…},"legend":{…},"confidence":…}`; level = argmax.
- `noul` → `{"type":"noul","noul":0.73,"confidence":0.73}`.

## 3. Rules learned from the model card and issues (follow them)
1. **Use `choice` with neutral keys instead of `noul`** — noul can follow its labels rather than content on the English checkpoint.
2. **Gate on `confidence`, not `action.act_probability`** (the act head has no usable signal yet).
3. **Keep options ≤ 12**; for more, ask coarse-to-fine (category, then sub-choice). Laya is weak with >20 options.
4. **Probabilities are over-confident out of the box**; calibrate (§5) before trusting thresholds.
5. **Zero-shot accuracy on complex decisions is low** (vendor: 0.362 vs 0.461 majority baseline on typed-decisions);
   fine-tuned 0.766. Hence: shadow first, our own labels, fine-tune later.
6. State text: title + sender + first ~600 chars of body, cleaned with `as_data()`; same builder for live calls,
   evals and training export (`triage/questions.py::state_text`) so train/serve never drift.

## 4. Modes (per tenant, per niche override)
| Mode | Behaviour |
|---|---|
| `off` | LLM fallback classifier answers the same questions (same JSON shape, `decided_by: llm_fallback`) |
| `shadow` | Laya answers stored; LLM fallback decides; shadow report compares |
| `on` | Laya decides when `confidence ≥ niche.triage.min_confidence`; below → LLM fallback for that question only |
Failure handling: transport error/timeout (10 s) → `None` per state → fallback. Never raise into the pipeline.

## 5. Calibration and the "switch on" gate (phase 2 → 8)
- Labels: human decisions (gold), else LLM fallback answers on items the human did not touch (silver, weight 0.5).
- `python -m app.feedback.shadow_report --niche news_radar --days 14` → per cutoff: decided, agreed, **wrong**.
- Switch a niche to `on` when, at its `min_confidence`, Laya decides ≥ 50 % of items with ≤ 3 % wrong vs gold
  and 0 wrong on `risk = scam_or_phishing`. Record the decision in `docs/adr/`.
- Temperature fit: `triage/calibration.py` fits one temperature per question type on held-out feedback (minimise
  NLL), stored in `tenant_settings.laya_temperatures`; applied to probabilities before gating.

## 6. Evals
`evals/<niche>.jsonl`, one row per line, laya-evals format:
```json
{"state": "…", "questions": {"keep": {…}}, "expected": {"keep": "A"}, "tags": ["news_radar"], "language": "en"}
```
`make eval NICHE=news_radar` → runs `laya-evals run evals/news_radar.jsonl` against `LAYA_URL` (or the
Python API locally) and our LLM fallback on the same rows; prints accuracy, ECE, confusion, per-language slice.

## 7. Fine-tuning (phase 8)
- Export: `GET /v1/feedback/export?format=laya_train` → `{state, questions, gold}`; `gold` is per-question
  probabilities (hard label = 1.0 on the chosen key). Balance classes; hold out 15 % for eval.
- Train: the official Kaggle notebook (free 2×T4; ~45 min for a few thousand questions; `freeze_encoder=True`
  for a quick head-only run). Full fine-tune, not LoRA (a LoRA adapter alone is not a complete checkpoint).
- Gate: new checkpoint must beat the current one on the held-out eval (accuracy and ECE) and on every niche
  eval file; then push privately to the HF Hub and set `LAYA_MODEL=<repo>` for that tenant.
- Aim 1,000–3,000 labelled items per niche before the first fine-tune.

## 8. Sharing with Opportunity Radar
The radar's `app/laya_gate.py` (patch from the earlier session) calls the same `/v1/systemone/batch`. Run one
`laya` service and point both `LAYA_URL`s at it, each with its own load (≤ 4 concurrent each).
