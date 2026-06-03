# Implementation Plan - Expose Agent Capabilities Endpoint

Expose agent configuration details and capabilities to other applications through the Bifrost API. This enables upstream orchestrators, client applications, and sidecars to inspect agent personas, enabled tools, retrieval features (RAG/KG/PageIndex), and model configurations.

This endpoint exposes **persona IP** (system_prompt, personality_traits, greeting) and **attack-surface inventory** (tools, mcp_servers). Treat it as a sensitive read endpoint, not a public directory.

## User Review Required

> [!IMPORTANT]
> The decisions below must be locked before implementation starts. Defaults reflect the recommended path; flip them if the trade-off doesn't fit.

### 1. Authentication model — **LOCKED: (A) Yggdrasil JWT required**

`/v1/agents*` requires a valid Yggdrasil RS256 JWT. Tenant is derived from the `urn:zitadel:iam:org:id` claim. `X-Tenant-Id` header is **fallback only** (no JWT present) and emits a WARN log when used. Matches the Heimdall reference impl pattern.

Requests without a valid JWT and without an `X-Tenant-Id` header → `401 Unauthorized`. JWT tenant claim wins over `X-Tenant-Id` header when both present (header is ignored).

### 2. System prompt exposure
Exposed on the **detail** endpoint only, never on the list endpoint — limits IP leak surface and keeps list payloads small.

### 3. Dual identifier resolution
Detail endpoint accepts numeric `id` or `name`. If the path segment parses as `i64`, lookup is by `id`; otherwise by `name`. Documented caveat: an agent named `"42"` is unreachable by name. Acceptable because `agent_configs.unique_agent_name (tenant_id, name)` agents are conventionally named with letters (`eir`, `eir-cardio`, …).

### 4. Hard-excluded fields (never returned)
- `api_key`
- Anything added to `agent_configs` in the future (the SELECT is an explicit allow-list — new columns are invisible until explicitly added)

### 5. Whitelisted `rag_params` projection
`rag_params` is a free-form JSON column; today only `limit`, `alpha`, `output_format` are consumed ([overseer.rs:195-205](Bifrost/src/swarm_engine/overseer.rs#L195-L205)). Future code may stash secrets, collection names, or pricing hints there. Response projects **only** the known-safe keys; everything else is dropped.

### 6. Omitted-by-default fields
`template_id` is an internal implementation detail (which template the agent was cloned from). Omit unless a concrete consumer needs it — easier to add later than retract.

## Security Posture

### Acknowledged exposures (with mitigation)
| Exposure | Why it's sensitive | Mitigation |
|----------|-------------------|-----------|
| `system_prompt`, `personality_traits`, `greeting` | Curated clinical persona IP; Megawiz commercial differentiator | Detail endpoint only; auth gate per decision (1); audit per (M2) |
| `tools` + `mcp_servers` array | Tells attacker which downstream services this agent can reach → guides prompt-injection pivots toward Mimir/Syn/Hermodr | Accepted trade-off for introspection feature; same auth gate; rate limit per (M1) |
| `rag_params` raw blob | Free-form JSON could contain operator secrets in future | Whitelist projection per (5) |
| Cross-tenant existence | Per-tenant 403 leaks "this agent exists somewhere" | Single 404 code path with `WHERE id = ? AND tenant_id = ?` — same query/timing for "doesn't exist" vs "exists in another tenant"; miss logs at DEBUG not INFO (no probing oracle in Tyr/Loki) |
| `avatar_url` | Operator-controlled VARCHAR(500); could contain `javascript:`/data URIs | Document in response schema: clients must sanitize before rendering |

### Required controls (acceptance criteria — not nice-to-have)

- **(M1) Rate limiting**: tower-governor middleware on `/v1/agents*`, 60 req/min per source IP. Without this, an attacker enumerates `/v1/agents/1..9999` to map all agents and harvest prompts.
- **(M2) Tyr audit events**: emit structured event for **every detail endpoint access** (skip list — too noisy):
  ```json
  {"event": "agent.detail.read", "tenant_id": "...", "agent_id": 1, "agent_name": "eir-cardio",
   "caller_ip": "...", "jwt_sub": "... or null", "timestamp": "..."}
  ```
  Forward via Hermodr to Tyr. Detection rules to add to Tyr (separate ticket, not blocking): alert on `>N` agent detail reads/min per source; alert on detail reads where the same caller has never invoked `/run` on that agent before.
- **(M3) No SQL string-building**: resolution branching (`parse::<i64>` vs name) must select between two pre-bound queries, never concatenate. Locked in by test (T11 below) and code-review checklist.
- **(M4) Logging hygiene**: 404 misses log at DEBUG with the requested identifier; INFO-level logs omit the identifier to avoid building a probing oracle.

## Proposed Changes

### Bifrost Engine

#### [MODIFY] [main.rs](file:///Users/mimir/Developer/Bifrost/src/main.rs)

##### Explicit response column allow-list

Both endpoints select columns by **explicit allow-list** (never `SELECT *`) so that future columns added to `agent_configs` do not silently leak.

| Field             | List | Detail | Notes                                           |
|-------------------|------|--------|-------------------------------------------------|
| `id`              | ✅   | ✅     |                                                 |
| `name`            | ✅   | ✅     |                                                 |
| `display_name`    | ✅   | ✅     |                                                 |
| `description`    | ✅   | ✅     |                                                 |
| `avatar_url`     | ✅   | ✅     | client UI; operator-supplied — caller sanitizes |
| `greeting`       | ❌   | ✅     | persona IP — gated with system_prompt           |
| `is_published`   | ✅   | ✅     |                                                 |
| `model_id`       | ✅   | ✅     | inside `capabilities`                           |
| `provider`       | ✅   | ✅     | inside `capabilities`                           |
| `temperature`    | ✅   | ✅     | inside `capabilities`                           |
| `max_tokens`     | ✅   | ✅     | inside `capabilities`                           |
| `top_k`          | ✅   | ✅     | inside `capabilities`                           |
| `use_rag`        | ✅   | ✅     | inside `capabilities`                           |
| `use_knowledge_graph` | ✅ | ✅   | inside `capabilities`                           |
| `use_pageindex`  | ✅   | ✅     | inside `capabilities`                           |
| `tools`          | ✅   | ✅     | JSON → `Vec<String>`, null → `[]`               |
| `mcp_servers`    | ✅   | ✅     | JSON → `Vec<String>`, null → `[]`               |
| `personality_traits` | ❌ | ✅   | persona IP — gated with system_prompt           |
| `rag_params`     | ❌   | ✅     | **whitelist projection** — only `{limit, alpha, output_format}` |
| `system_prompt`  | ❌   | ✅     | **detail only** — large TEXT + IP-sensitive     |
| `template_id`    | ❌   | ❌     | internal detail — omitted until consumer asks   |
| `api_key`        | ❌   | ❌     | **never** returned                              |
| `created_at`    | ❌   | ✅     | ISO-8601                                        |
| `updated_at`    | ❌   | ✅     | ISO-8601                                        |

##### `list_agents` (modify existing)

- Replace the current narrow SELECT with the **list allow-list** above.
- Returned JSON shape:
  ```json
  {
    "tenant_id": "...",
    "agents": [
      {
        "id": 1,
        "name": "eir-cardio",
        "display_name": "...",
        "description": "...",
        "avatar_url": "...",
        "is_published": true,
        "capabilities": {
          "model_id": "...",
          "provider": "...",
          "temperature": 0.7,
          "max_tokens": 2048,
          "top_k": 5,
          "use_rag": true,
          "use_knowledge_graph": false,
          "use_pageindex": false,
          "tools": ["vector_search", "ocr_extract"],
          "mcp_servers": []
        }
      }
    ]
  }
  ```
- **Backwards compatibility**: legacy top-level fields (`id`, `name`, `display_name`, `description`, `model_id`, `is_published`) preserved on each agent. `model_id` duplicated at top level **and** inside `capabilities` for one release; mark top-level as deprecated in code comment.
- NULL `tools` / `mcp_servers` JSON columns must serialize as `[]`, never `null` and never 500.

##### `get_agent` (new) — `GET /v1/agents/{agent_id_or_name}`

- Tenant resolution per decision (1): JWT claim preferred, `X-Tenant-Id` header fallback (default `"default"`).
- Identifier resolution: `path.parse::<i64>()` → query by `id`; else by `name`. Both branches use pre-bound SQL — never concat (M3).
- Returns **`404 Not Found`** with `{"error":"agent_not_found"}` on miss. Same status + same code path whether the agent doesn't exist anywhere or exists under a different tenant. Miss logs at DEBUG only (M4).
- Response shape = list-agent shape **plus** detail-only columns per the allow-list (subject to decision (1) split).
- Emits Tyr audit event per (M2) before returning the response. **Best-effort (fail-open)**: Tyr sink failure logs WARN but does not fail the request.

##### Routing
- `.route("/v1/agents/{agent_id_or_name}", get(get_agent))` — register **after** `/v1/agents/{agent_id}/run` so axum's exact-match for `/run` still wins. Locked by test (T10).

##### Middleware
- Apply tower-governor rate-limit layer scoped to `/v1/agents*`: **60 req/min per source IP** (M1).
- Apply JWT-validation middleware to the same scope (decision 1).

## Verification Plan

### Automated Tests

Build + existing suite:
```bash
DATABASE_URL=mysql://root:root@127.0.0.1:3306/mimir_test cargo check
DATABASE_URL=mysql://root:root@127.0.0.1:3306/mimir_test cargo test
```

New test cases (integration tests against seeded `mimir_test` DB):

1. **List shape** — `GET /v1/agents` returns `capabilities` nested object on every agent; legacy top-level fields still present.
2. **List excludes persona + secrets** — assert the strings `"system_prompt"`, `"personality_traits"`, `"greeting"`, `"api_key"`, `"rag_params"` never appear in serialized list response.
3. **Detail by id** — `GET /v1/agents/1` returns agent with id 1 for the matching tenant.
4. **Detail by name** — `GET /v1/agents/eir-cardio` returns same agent as (T3) when ids align.
5. **Detail excludes `api_key` and `template_id`** — even when DB row's `api_key`/`template_id` are non-null, response must not contain those keys.
6. **`rag_params` whitelist** — seed agent with `rag_params = {"limit":10, "alpha":0.5, "output_format":"json", "secret_key":"hunter2", "internal_collection":"private"}`. Detail response contains only `limit`/`alpha`/`output_format`; `secret_key` and `internal_collection` are dropped.
7. **Cross-tenant isolation (no leak)** — seed agent under tenant `A`. Request with `X-Tenant-Id: B` → `404` body `{"error":"agent_not_found"}`. Must not be 403; response must not contain agent metadata; log assertion: identifier appears at DEBUG only, not INFO (M4).
8. **Draft filtering on list** — unpublished agent hidden by default; visible with `?include_drafts=true`.
9. **NULL JSON columns** — agent with `tools = NULL`, `mcp_servers = NULL`, `personality_traits = NULL` → response has `[]`, not `null`, not 500.
10. **Route precedence** — `POST /v1/agents/1/run` still routes to `run_agent`, not `get_agent`.
11. **Numeric-name edge case** — agent named `"42"` is reachable as `/v1/agents/42` resolving by id (documented behavior); test locks in resolution order.
12. **Rate limit (M1)** — fire >60 detail requests/min from one source → some receive `429 Too Many Requests`.
13. **Audit emission (M2)** — detail endpoint hit produces an `agent.detail.read` event with required fields (capture via test harness intercepting the Tyr sink).
14. **JWT path** — request without valid JWT and no `X-Tenant-Id` → `401`. Request with JWT whose tenant claim mismatches `X-Tenant-Id` → JWT wins, header silently ignored (assert response tenant_id matches JWT claim).

### Manual Verification

```bash
# Happy path
curl -H 'X-Tenant-Id: asgard_medical' http://localhost:8080/v1/agents | jq
curl -H 'X-Tenant-Id: asgard_medical' http://localhost:8080/v1/agents/eir-cardio | jq

# Drafts
curl -H 'X-Tenant-Id: asgard_medical' 'http://localhost:8080/v1/agents?include_drafts=true' | jq

# Cross-tenant probe — must return 404, no agent fields
curl -i -H 'X-Tenant-Id: nonexistent' http://localhost:8080/v1/agents/eir-cardio

# Field-leak grep — response bodies must not contain api_key or rag_params keys outside the whitelist
curl -H 'X-Tenant-Id: asgard_medical' http://localhost:8080/v1/agents | grep -E 'api_key|secret' && echo "LEAK" || echo "OK"

# Rate limit
for i in $(seq 1 100); do curl -s -o /dev/null -w '%{http_code}\n' \
  -H 'X-Tenant-Id: asgard_medical' http://localhost:8080/v1/agents/eir-cardio; done | sort | uniq -c
# expect a mix of 200 and 429
```

### Pre-merge checklist
- [ ] All 14 automated tests passing
- [ ] Manual field-leak grep returns OK
- [ ] Tyr audit pipeline receiving `agent.detail.read` in staging
- [ ] JWT validation tested against Yggdrasil test issuer
- [ ] Header-fallback path emits WARN log as designed