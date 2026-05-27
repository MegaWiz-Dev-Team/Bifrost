# Design — Skill-Loader Runtime (Bifrost Overseer)

- **Status:** Draft / Proposed
- **Date:** 2026-05-22
- **Implements:** the "missing piece" §5 of
  `Eir/docs/design/medical-agent-architecture.md` ("Agents = boundaries, Skills
  = expertise"). Read that first for the *why*; this doc is the *how*.
- **Touches:** `Bifrost/src/swarm_engine/overseer.rs` (agent loop), Mimir
  (skill registry + retrieval), MedOpenClaw (skill source), Hermodr (tool
  dispatch), Skuggi (safety), Tyr (audit), heimdall-trace (observability).
- **Companion:** context budgeting in `docs/design/agent-memory-evolution.md`
  (progressive disclosure shares the same token accounting).

---

## 1. What the loader is

A request-time stage in the overseer that turns *one query* + *one boundary
agent* into a *composed context* by **retrieving** the relevant expertise
modules (skills) and folding them in — instead of routing to a cloned
per-specialty agent.

Three hard invariants (everything below upholds these):

1. **Selection is retrieval, never an LLM call.** Cosine match over skill
   `description` embeddings — reuses the BGE-M3 + Qdrant infra already behind
   `/api/v1/knowledge/search`. (Removes the ~150–400ms `eir-router` LLM hop.)
2. **Skills only NARROW, never EXPAND.** A skill can subset the agent's tool
   ceiling, add constraints, and pin a *safer/local* model — it can never grant
   a tool the agent lacks, weaken a safety floor, or escalate to a cloud model.
3. **Degrade to the bare agent.** Registry down / nothing over the score floor →
   run the agent with base CoT and no skills (today's behaviour). Skills are
   additive; their absence is never an error.

---

## 2. Data model

### 2.1 Skill record (registry)

Sourced from the MedOpenClaw `SKILL.md` frontmatter (already cataloged in
B-49b). Stored in Mimir as `agent_skills` + a Qdrant collection
`skills-catalog` holding the `description` embedding.

```jsonc
{
  "skill_id":   "cardio-acs-workup",
  "name":       "Acute Coronary Syndrome workup",
  "description": "…",            // the ONLY field that is embedded/matched
  "specialty":  "cardiology",
  "reasoning_frame": "…",         // domain CoT (the ex-preamble)
  "allowed_tools":   ["search_primekg","search_clinical_kb","pubmed_search"],
  "knowledge_scope": { "collection": "clinical-wisdom",
                       "filter": { "specialty": "cardiology" } },
  "model_hint":   null,           // null = inherit agent; else a SAFER/local model only
  "safety_flags": [],             // e.g. ["require_hitl"]
  "version":      "2026.05",
  "status":       "active"        // active | draft | retired
}
```

### 2.2 Agent (host) — from §3 of the architecture doc

The loader reads, per request, from the resolved agent: `tool_ceiling` (= the
`agent_configs.tools` column; the enforced *maximum* set), `model_id`,
`allowed_models` (the local models a skill may pin to), and `safety_class`.
(`access_scope` is deferred — see `medical-agent-architecture.md` §3/§12, forensic
boundary postponed.)

> **Agent resolution happens BEFORE this loader** and is **not** part of it. The
> deterministic agent-resolver (`medical-agent-architecture.md` §4b — replaces
> `eir-router`) picks the boundary agent from structured signals (FHIR age, order
> intent) and is safety-critical. By the time the loader runs, `agent_id` is
> fixed. The loader never changes the agent.

---

## 3. The pipeline (per turn, in the overseer)

Inserted **after** `load_agent_config(...)` and **before** prompt/tool assembly
in `overseer.rs`.

```
                 query, agent_id, tenant_id
                          │
   ┌──────────────────────▼───────────────────────┐
   │ ① RESOLVE AGENT                               │  (existing load_agent_config)
   │   → tool_ceiling, model_id, safety_class      │
   └──────────────────────┬───────────────────────┘
                          │
   ┌──────────────────────▼───────────────────────┐
   │ ② SELECT SKILLS  →  POST /api/v1/skills/select │  (Mimir; embedding, NOT LLM)
   │   top_k + score_floor τ + MMR diversity        │
   └──────────────────────┬───────────────────────┘
                          │ ranked skills (frame, tools, scope, flags)
   ┌──────────────────────▼───────────────────────┐
   │ ③ COMPOSE CONTEXT  (progressive disclosure)    │
   │   base CoT + Σ reasoning_frame (score order)   │
   │   retrieval filtered by Σ knowledge_scope      │
   └──────────────────────┬───────────────────────┘
                          │
   ┌──────────────────────▼───────────────────────┐
   │ ④ INTERSECT TOOLS                              │
   │   effective = ceiling ∩ ⋃ skill.tools          │
   │   (no active skills → effective = ceiling)     │
   └──────────────────────┬───────────────────────┘
                          │
   ┌──────────────────────▼───────────────────────┐
   │ ⑤ APPLY SAFETY/MODEL                           │
   │   safety = agent.class ⊔ ⋃ skill.flags         │
   │   model  = skill.hint if ∈ allowed_models      │
   │           else agent.model_id                  │
   └──────────────────────┬───────────────────────┘
                          │
   ┌──────────────────────▼───────────────────────┐
   │ ⑥ EXECUTE (existing overseer loop)             │
   │   + ⑦ AUDIT skill set + denied tools → Tyr     │
   └────────────────────────────────────────────────┘
```

### 3.1 ② Selection — the Mimir contract

Selection lives **behind a Mimir endpoint** so embeddings + Qdrant stay in one
place (no embed model duplicated into Bifrost):

```
POST /api/v1/skills/select
{ "query": "...", "agent_id": "eir-clinical", "tenant_id": "asgard_medical",
  "top_k": 4, "score_floor": 0.35 }

200 → { "skills": [
  { "skill_id": "...", "name": "...", "score": 0.71,
    "reasoning_frame": "...", "allowed_tools": [...],
    "knowledge_scope": {...}, "safety_flags": [...], "model_hint": null },
  ... ], "total": 2, "elapsed_ms": 18 }
```

Mimir side: embed `query` (BGE-M3) → Qdrant search `skills-catalog` (filter
`status='active'`, optional specialty pre-filter) → **MMR re-rank** so we don't
return five near-duplicate cardiology skills → apply `score_floor` → return ≤
`top_k`. Empty result is valid (→ bare agent).

### 3.2 ③ Compose — progressive disclosure

- **Always cheap:** the agent base CoT.
- **Pinned by score:** selected skills' `reasoning_frame`, highest score first.
- **Retrieval:** the existing `manual_context` builders run **scoped** —
  vector/graph/tree searches filtered by the union of selected
  `knowledge_scope`s (so a cardiology query pulls cardiology-tagged chunks).
- **Under context pressure** (the 75% watermark from
  `agent-memory-evolution.md`): drop the **lowest-scored skill body first** —
  never the base CoT, never a `require_hitl`/safety frame.

> **`reasoning_frame` is advisory and subordinate — the one place "narrow-only"
> needs help.** Tool/model/safety-flag narrowing is structurally enforced, but a
> `reasoning_frame` is free text: a *confidently mis-retrieved* skill could inject
> misleading domain framing. Guards: (a) a **score floor** below which a skill's
> frame is NOT injected (a weak match should not reframe the answer); (b) the
> agent's **base CoT + safety preamble are pinned and authoritative** — frames are
> appended after them and may never override them; (c) on conflict with a
> `safety_flag`, the safety frame wins. Selection ranking ≠ permission to reframe.

Today `overseer.rs` mounts whatever is in `agent_configs.tools` and only logs a
warning for unknowns — there is no deny. Replace the mount source with the
computed effective set, and enforce at dispatch:

**Terminology:** there is exactly ONE tool set on the agent — the **ceiling**
(`agent_configs.tools`, the enforced maximum). There is no separate "base"
column. When skills are active, the loader *narrows* the exposed set to what
those skills declare (reduces tool-confusion for the model); when no skill is
active, the full ceiling is exposed.

```rust
// effective = ceiling ∩ (⋃ active skill.allowed_tools);  no skills → ceiling
fn effective_tools(ceiling: &HashSet<&str>, skills: &[Skill]) -> HashSet<String> {
    if skills.is_empty() {
        return ceiling.iter().map(|s| s.to_string()).collect();   // bare agent: full ceiling
    }
    skills.iter()
        .flat_map(|s| s.allowed_tools.iter().map(String::as_str))
        .filter(|t| ceiling.contains(t))   // ceiling is the hard cap — skills never exceed it
        .map(String::from)
        .collect()
}
```

- The result is the mount list (replaces direct use of `agent_configs.tools`).
- **Dispatch-time deny:** any tool call outside the effective set is rejected at
  the overseer→Hermodr boundary and emitted to **Tyr** (deny-by-default).
- A skill listing a tool the agent ceiling lacks is dropped from that skill's
  contribution (logged, not fatal) — this is the *narrow-only* invariant in
  code, and exactly why pediatric `dosage_calculator` can never leak onto
  `eir-clinical`.

### 3.4 ⑤ Safety & model — narrow-only

```
safety_class_effective = agent.safety_class ⊔ ⋃ skill.safety_flags   // can only ADD
model_effective        = skill.model_hint  iff skill.model_hint ∈ agent.allowed_models
                         else agent.model_id        // membership check, not a "safer" ordering
```

LOCAL-only stays an agent-layer invariant: any non-local `model_hint` is
ignored. `require_hitl` from any active skill forces the human-in-loop path.

---

## 4. Interaction with the existing two execution paths

`overseer.rs` already has two modes — the loader feeds both:

| Path | How skills fold in |
|------|--------------------|
| **Native tool-calling** | Effective tool set (§3.3) is the mounted tool list; reasoning_frames go into the preamble. |
| **Heimdall/Gemini bypass** (tools pre-executed, results injected as `[… Results]` blocks) | Skill `reasoning_frame` → preamble; skill-scoped retrieval → the same context-block injection already used. No tool-calling needed. |

So the loader is orthogonal to the bypass mechanism — it changes *what* gets
mounted/injected, not *how*.

> ⚠️ **Phase-2 enforcement must be tested *with* the bypass injector, not just
> native tool-calling.** The bypass path auto-calls `query`-param tools (e.g.
> `primekg_disease_relations`) on behalf of local models. Deny-by-default (§3.3)
> must allow any such call **whose tool is in the effective set** — the
> enforcement is on the *tool*, applied identically to both paths. Regression
> risk: a ceiling/deny check that only understands native tool-calls could
> silently break the bypass path's grounding calls. Test both paths together.

---

## 5. Failure modes & degradation

| Condition | Behaviour |
|-----------|-----------|
| `/skills/select` unreachable / errors | Log, run **bare agent** (base CoT, ceiling tools). Never block the turn. |
| No skill ≥ `score_floor` | Empty set → bare agent (generic reasoning). Correct for off-domain queries. |
| Skill references unknown/over-ceiling tool | Drop that tool from the skill; keep the rest; log to Tyr. |
| Selection slow (p99) | Hard timeout (e.g. 300ms) → treat as empty set; the turn proceeds. |

---

## 6. Selection tuning (gated by data)

- `top_k` default **4**, `score_floor` **~0.35** (tune on specialty-tagged
  traffic — see architecture doc §11 parity test).
- `N_max` co-active skills (cap to bound context bloat) — start at `top_k`.
- **MMR diversity** (λ≈0.7) to avoid near-duplicate skills crowding out a second
  relevant specialty (the cardiology+nephrology case).
- Optional: per-session cache of `query → skill_ids` for identical repeats.

---

## 7. Observability (heimdall-trace + Tyr)

Every turn emits: selected `skill_id`s + scores, dropped/denied tools,
effective model, selection latency. This is both the **parity-test signal**
(skill-loader vs per-specialty agent on HBp) and the **audit trail** (which
expertise + tools touched a clinical answer).

---

## 8. Rollout

1. **MVP** — `/skills/select` (embedding retrieval, MMR) + inject
   `reasoning_frame` only. **No tool changes yet.** Measure parity on the
   specialty-tagged HBp subset.
2. **Tool intersection + dispatch deny** (§3.3) — close the warn-only gap; wire
   Tyr deny events.
3. **Scoped retrieval** (§3.2) — `knowledge_scope` filters on the existing
   search builders.
4. **Progressive disclosure** — hook into the 75% context watermark.
5. **Scale** — fold in the rest of the 869 cataloged skills; deprecate
   `eir-router`.

Each phase is independently shippable and individually measurable.

---

## 9. Open questions

- `score_floor` / `top_k` / MMR λ — fit to real traffic before freezing.
- Does `knowledge_scope.filter` map cleanly onto current Qdrant payload tags, or
  do clinical-wisdom chunks need a `specialty` tag backfill first?
- Skill embedding refresh: skills are clinical content that will be edited —
  re-embed on `version` bump; who triggers it (ties to the Mimir curator track)?
- Cross-boundary fan-out (e.g. prescription → mandatory `eir-pharmacy`): does the
  loader emit a *delegation signal*, or does the overseer keep that as a separate
  orchestration rule above the loader? (Lean: orchestration rule above the loader.)
- Selection cache invalidation across skill `version` bumps.