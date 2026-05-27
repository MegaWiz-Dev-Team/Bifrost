# Phase A: RL System Backend Integration

## Overview
Phase A implements the complete Multi-Agent Reinforcement Learning governance backend for Bifrost. All components are integrated and deployable to K8s.

## Components Implemented

### 1. Core RL Modules (6 modules)
- **rl_feedback.rs** — Feedback scoring (quality, relevance, latency, confidence)
- **rl_agent_self_eval.rs** — Agent self-evaluation & improvement proposals
- **rl_governance_voting.rs** — Odin + Frigg consensus voting
- **rl_safe_deployment.rs** — Canary & staged rollout with monitoring
- **rl_audit_trail.rs** — Compliance audit logging
- **rl_orchestrator.rs** — RL system coordinator

### 2. Background Tasks
- **rl_scheduler.rs** — Daily RL cycle at 02:00 UTC for [asgard_medical, asgard_insurance, asgard_platform]
- **rl_deployment_monitor.rs** — 30-second deployment health checks
- **rl_admin_routes.rs** — Admin API endpoints for manual triggers & status queries

### 3. Integration Points
- **run_agent()** — POST /v1/agents/{agent_id}/run ✅ Feedback logging hook
- **dispatch_agent()** — POST /v1/agents/dispatch ✅ Feedback logging hook
- **main.rs** — Scheduler/monitor spawning, admin router registration

## API Endpoints

### Admin Endpoints (POST /api/v1/...)

#### 1. Trigger Daily RL Cycle
```bash
GET /api/v1/rl/trigger-daily-cycle?tenant_id=asgard_medical
```
Response: `{ status: "success", message: "...", timestamp: "..." }`

#### 2. Check Active Deployments
```bash
GET /api/v1/rl/check-deployments
```
Response: `{ status: "success", deployments: [...] }`

#### 3. Get Agent RL Status
```bash
GET /api/v1/rl/agent-status?tenant_id=asgard_medical&agent_id=1
```
Response: `{ agent_id: 1, avg_quality: 0.85, conversations: 42, ... }`

## Database Schema

### Tables Created/Modified
1. `agent_feedback_logs` — Per-dispatch feedback (quality_score, relevance_score, latency_score, confidence_score)
2. `agent_rl_daily_metrics` — Daily aggregated metrics (avg_quality, conversations, improvement_opportunity)
3. `skill_improvement_proposals` — Proposed improvements from self-eval
4. `governance_votes` — Odin + Frigg approval votes
5. `skill_deployment_log` — Deployment phase tracking (canary→staged→full)
6. `rl_audit_events` — Compliance audit trail
7. `rl_audit_events_view` — Compliance violations flagged

### Key Columns Added
- `skill_deployment_log.deployment_percentage` — Current traffic %
- `skill_deployment_log.quality_score_baseline` — Baseline before deployment
- `skill_deployment_log.phase_start_time` — When phase started
- `skill_deployment_log.phase_config` — JSON config for each phase

## Build & Deployment

### Docker Build
```bash
# Local build (uses SQLX_OFFLINE with cached queries)
docker build -f Bifrost/Dockerfile -t asgard-bifrost:latest .
```

#### Build Configuration
- `SQLX_OFFLINE=true` — Offline query validation using cached .sqlx/ metadata
- `.sqlx/` — Copied from Mimir ro-ai-bridge (23 query cache files)
- Multi-stage: dependency caching, then source build

### K8s Deployment
```bash
# Deploy to K8s
bash ./scripts/k3s-deploy.sh bifrost

# Or force pod restart
kubectl rollout restart deployment/bifrost -n asgard
```

#### Pod Configuration
- Image: `asgard-bifrost:latest` (with imagePullPolicy: Never for local builds)
- Port 8100: Agent API + admin endpoints
- Environment: DATABASE_URL (set in pod, not Dockerfile)
- Healthz: `/healthz` → "OK"

## Testing Phase A

### Prerequisites
```bash
# Ensure Bifrost pod is running
kubectl get pods -n asgard -l app=bifrost

# Port-forward for local testing (optional)
kubectl port-forward -n asgard svc/bifrost 8100:8100 &
```

### Test Script
```bash
chmod +x tests/test_phase_a.sh
./tests/test_phase_a.sh
```

### Manual Tests

**1. Health Check**
```bash
curl http://localhost:8100/healthz
# Expected: "OK"
```

**2. Trigger Daily Cycle**
```bash
curl http://localhost:8100/api/v1/rl/trigger-daily-cycle?tenant_id=asgard_medical
# Expected: { "status": "success", ... }
```

**3. Check Deployments**
```bash
curl http://localhost:8100/api/v1/rl/check-deployments
# Expected: { "status": "success", "deployments": [...] }
```

**4. Get Agent Status**
```bash
curl http://localhost:8100/api/v1/rl/agent-status?tenant_id=asgard_medical&agent_id=1
# Expected: { "agent_id": 1, "avg_quality": 0.85, ... }
```

**5. Dispatch with Feedback Logging**
```bash
curl -X POST http://localhost:8100/v1/agents/dispatch \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: asgard_medical" \
  -d '{
    "source_agent_id": "eir",
    "target_agent_id": "1",
    "message": "What is HTN treatment?"
  }'
# Expected: { "final_answer": "..." } + feedback logged to agent_feedback_logs
```

### Verify Feedback Logging
```sql
SELECT COUNT(*) as feedback_count FROM agent_feedback_logs
WHERE tenant_id = 'asgard_medical' AND created_at > NOW() - INTERVAL 1 MINUTE;

SELECT dispatch_id, quality_score, relevance_score, latency_score
FROM agent_feedback_logs ORDER BY created_at DESC LIMIT 5;
```

## Known Limitations

### Phase A Scope (Backend Only)
- ❌ No frontend (Odin dashboard) — Phase B
- ❌ No real canary deployment mechanics — Phase D
- ❌ No actual skill improvement deployment — Phase D
- ✅ Feedback collection & storage working
- ✅ Admin endpoints callable
- ✅ Background tasks spawning

### Database Constraints
- Votes table supports Odin + Frigg only (2 voters)
- Skill improvement proposals are stored but not auto-applied
- Canary rollback triggers are configured but require Phase D deployment logic

## Verification Checklist

- [ ] Docker builds successfully with SQLX_OFFLINE
- [ ] Bifrost pod runs without errors (`kubectl logs ...`)
- [ ] Healthz endpoint responds: `curl http://localhost:8100/healthz`
- [ ] Admin endpoints respond: `/api/v1/rl/trigger-daily-cycle`
- [ ] Dispatch calls create feedback logs: `SELECT * FROM agent_feedback_logs`
- [ ] Daily cycle scheduler runs (check logs for "RL cycle completed")
- [ ] Deployment monitor runs (check logs for "Checking deployments")

## Next Steps → Phase B

Once Phase A is verified:
1. **Phase B** (Frontend Dashboard) — React UI for Odin approval interface
2. **Phase C** (Testing Framework) — Comprehensive test suite
3. **Phase D** (Real Deployment) — Actual canary rollouts with metrics
4. **Phase E** (Documentation) — User guides & operational runbooks

---

**Status**: ✅ Complete & Deployable
**Last Updated**: 2026-05-28
