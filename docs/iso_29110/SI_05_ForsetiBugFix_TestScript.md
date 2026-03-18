# SI-05 TDD Bug Fix — Forseti-Driven Issue Resolution

## Document Info
| Item | Value |
|------|-------|
| Project | Asgard AI Platform — Bifrost |
| Phase | SIT (System Integration Testing) |
| Author | AI Engineering Team |
| Date | 2026-03-18 |
| ISO Reference | ISO/IEC 29110-5-1-2 SI.4 |

## 1. Source — Forseti Test Dashboard

| Run ID | Service | Suite | Status | Failing Scenario |
|:------:|---------|-------|:------:|------------------|
| #4 | Bifrost | E2E Tests | 10/11 | B07: `POST /v1/agents/default/run` → 422 |
| #3 | Mimir | UI Tests | 3/4 | `GET Docker /healthz` → 404 |

## 2. Root Cause Analysis

### Bug 1: Bifrost Agent Run — 422 Unprocessable Entity
- **Symptom**: `POST /v1/agents/default/run` with OpenAI `messages` format returns 422
- **Root Cause**: `RunRequest.input` is required `str`, no `messages` field
- **Impact**: All OpenAI-compatible agents cannot use Bifrost agent runtime

### Bug 2: Mimir Docker — /healthz Returns 404
- **Symptom**: Docker image doesn't have `/healthz` route
- **Root Cause**: Docker image predates `/healthz` alias addition
- **Impact**: Kubernetes liveness probes fail

## 3. TDD Cycle — Bug 1 (Bifrost)

### 3.1 RED Phase — Failing Tests
```
tests/test_api.py::TestAgentEndpoints::test_run_with_messages_format FAILED
tests/test_api.py::TestAgentEndpoints::test_run_messages_extracts_last_user_content FAILED
```
- `assert 422 == 200` — Confirms the bug

### 3.2 GREEN Phase — Fix Applied
**File**: `bifrost/api/agents.py`

```python
class RunRequest(BaseModel):
    input: str | None = None
    messages: list[dict] | None = None  # OpenAI-compatible

    @model_validator(mode="after")
    def extract_input_from_messages(self):
        if self.input is None and self.messages:
            for msg in reversed(self.messages):
                if msg.get("role") == "user" and msg.get("content"):
                    self.input = msg["content"]
                    break
        if not self.input:
            raise ValueError("Either 'input' or 'messages' required")
        return self
```

### 3.3 VERIFY Phase — All Tests Pass
```
tests/test_api.py::TestAgentEndpoints::test_run_requires_input_or_messages PASSED
tests/test_api.py::TestAgentEndpoints::test_run_with_input_format PASSED
tests/test_api.py::TestAgentEndpoints::test_run_with_messages_format PASSED
tests/test_api.py::TestAgentEndpoints::test_run_messages_extracts_last_user_content PASSED
4 passed in 0.15s
```

## 4. Re-Test Results (Post-Fix)

| Run ID | Service | Before | After | Delta |
|:------:|---------|:------:|:-----:|:-----:|
| #7 | Bifrost | 10/11 | **11/11** | +1 ✅ |
| #8 | Yggdrasil | 8/8 | **8/8** | — |
| #9 | Heimdall | 1/5 | 1/5 | — (external) |

## 5. GitHub Issues
- Bifrost: Issue created for `RunRequest` messages format
- Mimir: [#254](https://github.com/MegaWiz-Dev-Team/Mimir/issues/254) — Docker rebuild blocked by cargo error

## 6. Sign-Off
- [x] Root cause identified from Forseti data
- [x] TDD RED tests written and confirmed failing
- [x] GREEN fix implemented
- [x] All unit tests pass (4/4)
- [x] E2E re-test shows improvement (10/11 → 11/11)
- [x] Results submitted to Forseti Dashboard
