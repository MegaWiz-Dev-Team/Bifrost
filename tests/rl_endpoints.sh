#!/bin/bash
# Test RL Phase A endpoints

PORT=8100
BASE_URL="http://localhost:$PORT"
TENANT_ID="asgard_medical"

echo "=== Testing RL Phase A Endpoints ==="
echo

# 1. Trigger daily RL cycle
echo "1. Trigger daily RL cycle"
curl -s -X GET "${BASE_URL}/api/v1/rl/trigger-daily-cycle?tenant_id=${TENANT_ID}" \
  -H "Content-Type: application/json" | jq .
echo

# 2. Check deployments
echo "2. Check active deployments"
curl -s -X GET "${BASE_URL}/api/v1/rl/check-deployments" \
  -H "Content-Type: application/json" | jq .
echo

# 3. Get agent RL status
echo "3. Get agent RL status (agent_id=1)"
curl -s -X GET "${BASE_URL}/api/v1/rl/agent-status?tenant_id=${TENANT_ID}&agent_id=1" \
  -H "Content-Type: application/json" | jq .
echo

# 4. Run agent dispatch and verify feedback logging
echo "4. Run A2A dispatch to trigger feedback logging"
curl -s -X POST "${BASE_URL}/v1/agents/dispatch" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: ${TENANT_ID}" \
  -d '{
    "source_agent_id": "eir",
    "target_agent_id": "1",
    "message": "What is the standard treatment for HTN?"
  }' | jq .
echo

echo "=== Tests Complete ==="
