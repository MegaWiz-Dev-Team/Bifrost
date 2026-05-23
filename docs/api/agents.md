# Bifrost API — Agent Capabilities

Endpoints for inspecting agent configuration and capabilities. Companion design doc: [agent_list_implementation_plan.md](../design/agent_list_implementation_plan.md).

- `GET /v1/agents` — list agents available to the calling tenant
- `GET /v1/agents/{agent_id_or_name}` — detail view for one agent

> [!IMPORTANT]
> These endpoints expose **persona IP** (`system_prompt`, `personality_traits`, `greeting`) and **attack-surface inventory** (`tools`, `mcp_servers`). They are not a public directory — treat them like authenticated admin reads.

## Authentication

Both endpoints require a tenant context resolved by one of:

1. **Yggdrasil JWT** (preferred). `Authorization: Bearer <RS256-jwt>`; tenant is derived from the `urn:zitadel:iam:org:id` claim. Requires server-side env vars `YGGDRASIL_ISSUER` + `JWT_AUDIENCE=bifrost`.
2. **`X-Tenant-Id` header** (fallback). Used only when no JWT is presented. Each call emits a `WARN`-level log so operators can spot header-only callers.

Neither path supplied → **`401 Unauthorized`**.

If both are present, the JWT wins and the header is silently ignored.

### Rate limit
60 requests per minute per source IP (`X-Forwarded-For` → `X-Real-IP` → `Forwarded` → peer IP). Excess returns **`429 Too Many Requests`**.

### Audit
Each successful `/v1/agents/{id}` access emits a structured `tracing` event:
```
event=agent.detail.read tenant_id=<...> agent_id=<...> agent_name=<...>
auth_path=jwt|header_fallback jwt_sub=<sub-or-empty>
```
The event flows through the OTLP pipeline to Tyr. List endpoint reads are **not** audited (too noisy for a directory view).

---

## `GET /v1/agents`

List agents available to the calling tenant. Returns published agents only by default.

### Query parameters
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `include_drafts` | `bool` | `false` | Set `1` / `true` / `yes` to include unpublished agents |

### Response — `200 OK`
```json
{
  "tenant_id": "asgard_medical",
  "agents": [
    {
      "id": 1,
      "name": "eir-cardio",
      "display_name": "Eir Cardiology",
      "description": "Specialty agent for cardiology questions",
      "avatar_url": "https://...",
      "is_published": true,
      "model_id": "gemma-4-26b",
      "capabilities": {
        "model_id": "gemma-4-26b",
        "provider": "mlx",
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

### Fields — list response
- Top-level `id`, `name`, `display_name`, `description`, `model_id`, `is_published` are preserved for backwards compatibility. New consumers should read from `capabilities`.
- `capabilities.tools` and `capabilities.mcp_servers` are always arrays (NULL DB columns serialize as `[]`).
- **Never present**: `system_prompt`, `personality_traits`, `greeting`, `rag_params`, `api_key`, `template_id`. These are detail-endpoint only or never returned at all.

---

## `GET /v1/agents/{agent_id_or_name}`

Detail view for one agent.

### Path resolution
- If `{agent_id_or_name}` parses as `i64` → looked up by `agent_configs.id`.
- Otherwise → looked up by `agent_configs.name`.
- Both branches are filtered on the caller's tenant.

> **Caveat**: an agent whose `name` is a string of digits (e.g. `"42"`) is unreachable by name via this endpoint — the path always resolves to ID first. Conventional names (`eir`, `eir-cardio`, …) are unaffected.

### Response — `200 OK`
```json
{
  "id": 1,
  "name": "eir-cardio",
  "display_name": "Eir Cardiology",
  "description": "...",
  "avatar_url": "https://...",
  "greeting": "Hello, I'm Eir's cardiology specialist.",
  "is_published": true,
  "model_id": "gemma-4-26b",
  "system_prompt": "You are a cardiology specialist...",
  "personality_traits": ["warm", "precise", "evidence-based"],
  "created_at": "2026-05-10T12:34:56+00:00",
  "updated_at": "2026-05-19T08:21:00+00:00",
  "capabilities": {
    "model_id": "gemma-4-26b",
    "provider": "mlx",
    "temperature": 0.7,
    "max_tokens": 2048,
    "top_k": 5,
    "use_rag": true,
    "use_knowledge_graph": true,
    "use_pageindex": false,
    "tools": ["vector_search", "graph_search", "primekg_search"],
    "mcp_servers": ["hermodr-mimir"]
  },
  "rag_params": {
    "limit": 10,
    "alpha": 0.7,
    "output_format": "json"
  }
}
```

### Detail-only fields
- `system_prompt`, `personality_traits`, `greeting`, `created_at`, `updated_at`.
- `rag_params` is a **whitelisted projection** — only `limit`, `alpha`, `output_format` are returned. Any other keys stored in the DB column (legacy tuning, operator notes, future config) are dropped before serialization.

### Never returned
- `api_key` — server-side credential, hard-excluded from every response.
- `template_id` — internal implementation detail.
- Any column added to `agent_configs` in the future, unless explicitly added to the SELECT allow-list in `src/agents.rs`.

---

## Error responses

| Status | Body | When |
|--------|------|------|
| `401 Unauthorized` | `{"error":"unauthorized","reason":"missing_credentials"\|"invalid_token"\|"invalid_tenant_claim"}` | No JWT and no `X-Tenant-Id`; or JWT failed validation |
| `404 Not Found` | `{"error":"agent_not_found"}` | Agent does not exist for this tenant — **same body and same code path** whether the agent is missing entirely or belongs to another tenant (no cross-tenant existence oracle) |
| `429 Too Many Requests` | (governor default body) | Rate limit exceeded for the source IP |
| `500 Internal Server Error` | `{"error":"internal_error"}` | DB connection failure or unexpected error. The actual error message is logged server-side; the response never echoes it |

---

## Examples

### List agents (header fallback)
```bash
curl -H 'X-Tenant-Id: asgard_medical' \
     http://localhost:8100/v1/agents | jq
```

### List including drafts (JWT auth)
```bash
curl -H "Authorization: Bearer $JWT" \
     'http://localhost:8100/v1/agents?include_drafts=true' | jq
```

### Detail by ID
```bash
curl -H "Authorization: Bearer $JWT" \
     http://localhost:8100/v1/agents/1 | jq
```

### Detail by name
```bash
curl -H "Authorization: Bearer $JWT" \
     http://localhost:8100/v1/agents/eir-cardio | jq
```

### Cross-tenant probe (must 404, never leak)
```bash
curl -i -H 'X-Tenant-Id: nonexistent' \
     http://localhost:8100/v1/agents/eir-cardio
# HTTP/1.1 404 Not Found
# {"error":"agent_not_found"}
```

### Field-leak grep (run after any handler change)
```bash
curl -s -H 'X-Tenant-Id: asgard_medical' \
     http://localhost:8100/v1/agents | \
  grep -E 'api_key|system_prompt|hunter2|rag_params'
# expect no output
```

---

## Backwards compatibility

The list response keeps these legacy top-level fields on each agent **for one release window**: `id`, `name`, `display_name`, `description`, `model_id`, `is_published`. New consumers should read from the nested `capabilities` object instead — the duplicated `model_id` will be removed in a subsequent release.

## Implementation reference
- Handler module: [src/agents.rs](../../src/agents.rs)
- Auth middleware: [src/middleware.rs](../../src/middleware.rs)
- JWT validator (ported from Heimdall): [src/auth_jwt.rs](../../src/auth_jwt.rs)
- Design doc + security posture: [docs/design/agent_list_implementation_plan.md](../design/agent_list_implementation_plan.md)
- Integration tests: [tests/agents_endpoint.rs](../../tests/agents_endpoint.rs)
