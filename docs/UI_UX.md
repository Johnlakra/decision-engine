# UI / UX

**Principle: one screen does 90 % of the job — the decision queue.** Everything else is setup.
The user should clear 20 decisions in under 2 minutes, and a farmer should get an answer by pressing one
button and speaking.

## 1. Inspiration (study, do not copy)
| Product | Take |
|---|---|
| Superhuman | speed, single-key actions, "inbox zero" feeling, command palette |
| Inbox Zero (open source) | plain-English rules, bulk unsubscribe, reply tracking |
| Linear triage | calm list, one item focused, keyboard-first, accept/decline/snooze |
| Tinder / Tinder-style review apps | swipe right/left/up on mobile, one card at a time |
| Things 3 / Todoist "Today" | one clear "what now" list, gentle visual hierarchy |
| Google News "For you" | topic chips, "less like this" |
| Kisan / agri apps used in Punjab (e.g. KVK advisories) | big type, icons, voice, local language first |

## 2. Information architecture
Web nav (left rail, collapsible): **Queue** (badge count) · History · Niches · Sources · Insights · Settings.
Mobile tabs: **Queue** · History · Settings (+ farmer mode = a different home: one big mic button).

## 3. Screens
### Queue (home)
- Header: "12 to decide · 3 urgent" + filter chips (All, niche chips, source chips) + bulk toggle.
- Card (one focused, others compact list on desktop; one card stack on mobile):
  - source icon + sender/feed · relative time · urgency dot (red/amber/grey) · deadline pill ("due today")
  - **one-line summary** (bold), 2-line context (muted)
  - **Recommended:** label of recommended option + confidence chip (High ≥ 0.8 / Medium / Low, never raw %)
  - "Why?" disclosure: rationale (≤ 3 sentences) + top Laya probabilities as small bars + evidence chips with data dates
  - Options as buttons (recommended first, primary style); risk banner if scam/phishing
- Keys: `a` approve recommended · `1–5` choose option · `r` reject · `e` edit · `s` snooze (later today / tomorrow / next week / pick) · `j/k` move · `o` open source · `?` help · `⌘K` command palette.
- After an action: card animates out, toast "Archived · Undo" for 10 s.
- Empty state: "All clear. Next digest at 9:00." + small summary of what was auto-handled today (link).
- Bulk mode: checkbox per card, "Approve recommended (8)".

### Item detail (drawer on desktop, full screen on mobile)
Tabs: Decision · Content (normalised) · Raw JSON · Triage (all Laya answers, mode, model, latency) · Activity (actions log).
Edit decision: change option, edit draft reply in a textarea, add note ("why I disagreed") → feeds learning.

### History
Search, filters (niche, verdict, decided_by, date). Row: summary, verdict, who/what decided, action result. "Teach":
mark a past decision as wrong → feedback correction.

### Niches
Cards per niche: enabled toggle, autonomy (Suggest / Ask first / Auto with digest), Laya mode (Off/Shadow/On, with
shadow report link), today's counts. Detail: form for description, questions, actions; "Advanced: YAML" editor with live
schema validation; "Test with an example" box that runs `/v1/decide`. "New niche" → wizard (describe in a sentence →
draft → edit → save).

### Sources
List with health dot, last sync, items today, error. Add: RSS (paste URL or search query), Gmail (connect), Instagram
(connect, professional only), Telegram (show bot link + code), Webhook (shows URL + secret + curl example), Upload (CSV).

### Insights
Today: items in / decided / auto-handled / discarded; time saved estimate; per-provider LLM budget bars; Laya
agreement % per niche; slowest decisions. Use the project chart conventions (accessible palette, no 3D, no pies > 4).

### Settings
Profile & timezone · Notifications (Telegram, push, digest hour, quiet hours, urgent ping cap/day) · Interests (for news)
· Languages · Privacy (private providers, retention) · API keys · Webhook subscriptions · Danger zone.

### Farmer mode (mobile, phase 7)
Home = big mic button "ਬੋਲੋ / Speak", last 3 answers as large cards with an icon (💧 irrigation, ₹ selling, 🐛 pest),
answer read aloud (TTS) with a replay button, "Ask the expert" button always visible. Onboarding: language → crop(s) →
village (pick from list) → consent. Font ≥ 18 px, contrast ≥ 7:1, works on 3G with offline cache of last answers.

## 4. Design tokens (shadcn/ui + Tailwind CSS variables; light and dark)
- Type: Inter (UI) + Noto Sans Gurmukhi / Noto Sans Devanagari for pa/hi; base 15 px web, 16 px mobile; scale 12/13/15/17/20/24/30.
- Radius 10 px cards, 8 px buttons; spacing 4-pt grid; card padding 16; max content width 760 for the queue.
- Color roles (not hues): `--bg`, `--surface`, `--surface-2`, `--text`, `--text-muted`, `--border`, `--primary`
  (approve), `--danger` (reject/scam), `--warning` (deadline), `--info`, `--focus`. Urgency uses icon + text, not color only.
- Motion: 150–200 ms ease-out; card exit slide 220 ms; respect `prefers-reduced-motion`.
- Icons: lucide; source icons as monochrome glyphs.

## 5. Components
Web (shadcn/ui): Card, Button, Badge, Tooltip, Dialog/Sheet (detail), Command (palette), Tabs, Toast (sonner),
Form (react-hook-form + zod), Textarea, Switch, Select, Table (TanStack Table) for History. Charts: Recharts.
Mobile: `react-native-gesture-handler` + `react-native-reanimated` SwipeCard (thresholds: 30 % width to commit,
haptic on commit, buttons under the card as alternative), expo-haptics, expo-notifications (category actions
approve/reject), expo-av/expo-audio for recording, NativeWind for styling with the same tokens.

## 6. Copy rules
Short, plain, second person ("You have 3 decisions due today"). Never "AI thinks"; say "Suggested". Confidence words
(High/Medium/Low), not percentages, in cards. Every automatic action is visible in History with "Undo" when possible.
All strings in `messages/{en,hi,pa}.json`.

## 7. Acceptance checklist (ui-ux-designer runs it every phase)
- [ ] Queue fully usable with keyboard only; visible focus ring; `?` lists shortcuts
- [ ] Every swipe has a button alternative; touch targets ≥ 44 px
- [ ] Contrast AA (AAA in farmer mode); works at 200 % zoom and 360 px wide
- [ ] Loading skeletons, empty states, error states with retry for every screen
- [ ] Undo after every queue action; no action without feedback
- [ ] hi and pa render correctly (fonts, line height), long words wrap
- [ ] Lighthouse a11y ≥ 95, performance ≥ 85 on the queue

## 8. Build status (Phase 3, 2026-10-14)
- Queue states built: loading, error with retry, empty, failed send (back in the queue), undo window.
- Keys built: a, r, 1–5, j, k, o, ?. Not built: s (snooze) and e (edit), which need the time picker and the detail view.
- Confidence: High >= 0.8 (spec), Medium >= 0.5 (our threshold, not in the spec), Low below.
- Undo is client-side: decisions are held 10 s and sent when the window closes. The API has no undo.
- Hindi and Punjabi strings are first drafts and need a native-speaker review before release.
- Fonts: Inter is named in the stylesheet but not loaded yet. shadcn/ui components are not added yet.

