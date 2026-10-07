---
description: Show Laya shadow results per niche and recommend which niches (if any) can switch to "on".
argument-hint: "[niche] [days]"
---
Run the shadow report (`python -m app.feedback.shadow_report $ARGUMENTS`, or via `docker compose exec worker …` when
running in compose). Then call `laya-integrator` to interpret it against the switch-on rule in docs/LAYA.md §5 and
propose per-niche: keep shadow / switch on at cutoff X / needs more labels / needs better description. Do not change any
mode; ask me first, then record an ADR for each switch.
