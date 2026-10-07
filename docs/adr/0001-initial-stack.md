# 0001 — Initial stack

**Status:** accepted · 2026-10-07

## Context
Personal-first decision engine that must run at ₹0, connect to other projects over HTTP, use Laya for fast
triage and free-tier LLMs for reasoning, and later scale to paying users. The owner's stack is React, Next.js,
React Native/Expo, FastAPI, MySQL, Redis.

## Decision
FastAPI + LangGraph (Python) for API and workers; Postgres + pgvector (not MySQL: pgvector, JSONB, LangGraph's
Postgres checkpointer); Postgres-table job queue (no Redis polling on Upstash); Laya as a separate `laya-serve`
service; LiteLLM-based gateway; Next.js web, Expo mobile; Docker Compose on an Oracle free VM first.

## Consequences
One new database to learn (Postgres) instead of MySQL. Laya needs a ≥ 4 GB machine. Everything else is
swappable by env. Changing any of this needs a new ADR.
