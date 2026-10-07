---
description: Add a new decision niche (YAML + evals + validation), started in Laya shadow mode.
argument-hint: "<one sentence: what decisions this niche makes>"
---
Create a niche for: $ARGUMENTS

1. Call `niche-designer` with the description. It writes `niches/<name>.yaml`, `evals/<name>.jsonl` (≥ 30 rows),
   validates against schemas/niche.schema.json, runs `make eval NICHE=<name>` and reports accuracy + confusing niches.
2. If the niche needs a tool or action that is not in the registries, call the right builder (`connector-builder`,
   `pipeline-builder`, `agri-domain-expert`, or `langgraph-builder` for custom steps) to add it with tests.
3. Call `code-reviewer` on the diff. Show me the YAML summary (description, questions, actions, autonomy) and eval
   numbers, and ask me to approve before committing. Laya mode for the new niche stays `shadow`.
