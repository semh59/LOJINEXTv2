---
description: Mandatory strict workflow rules for LOJINEXTv2 project
alwaysOn: true
---

# LOJINEXTv2 Agent Directives

You are an AI agent operating in the LOJINEXTv2 repository.
This project strictly follows an Agent-Driven Development Framework.
You are assumed to have NO memory between sessions. Every assumption must be verified against the project's markdown records.

**YOUR MANDATORY FIRST STEP:**
Before writing any code or answering any request, you MUST verify the project state by reading the following files in this exact order:

1. `.agents/docs/AGENTS.md`
2. `.agents/docs/WORKFLOW.md`
3. `.agents/docs/RULES.md`
4. `standards/PLATFORM_STANDARD.md`
5. `standards/SERVICE_REGISTRY.md`
6. `standards/DECISIONS.md`
7. `standards/KNOWN_ISSUES.md`
8. `MEMORY/PROJECT_STATE.md`

**CRITICAL RULES SUMMARY:**

- **Never skip the 7-Phase Workflow:** (READ → UNDERSTAND → PLAN → BUILD → PROVE → RECORD → HAND OFF).
- **No Code Without a Plan:** `PLAN.md` must be written/updated before code changes.
- **Record Everything:** Update `STATE.md`, `CHANGED_FILES.md`, and `TEST_EVIDENCE.md` incrementally. Do not wait until the end.
- **Always Leave a Handoff:** Before your session ends, write `TASKS/<active-task>/NEXT_AGENT.md`.
- **English Only:** All code and docs are strictly in English.
