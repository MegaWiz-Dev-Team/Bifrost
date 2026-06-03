# Bifrost RL Governance - K8s Deployment Guide

## Overview

Bifrost is deployed as a containerized Rust service in Kubernetes with:
- **2 replicas** minimum (auto-scales to 5 on high CPU/memory)
- **Health checks** (liveness + readiness probes)
- **Security policies** (non-root, read-only filesystem, network policies)
- **Resource limits** (500m CPU/512Mi memory min, 2000m/2Gi max)
- **SQLX_OFFLINE** enabled (no database access at build time)

## Prerequisites

1. **Kubernetes cluster** (1.24+) with metrics server
2. **Docker image** pushed to GHCR: `ghcr.io/asgard-ai/bifrost:latest`
3. **MariaDB** running at `mariadb.asgard.svc:3306`
4. **Mimir API** at `mimir-api.asgard.svc:8090`

## Deployment Steps

### 1. Create Namespace & Secrets

```bash
# Apply the entire manifest
kubectl apply -f k8s-manifest.yaml

# Verify namespace was created
kubectl get namespace asgard-rl
```

### 2. Update Database Credentials

The manifest includes a default secret. **Update it for your environment**:

```bash
kubectl create secret generic bifrost-db-secret \
  --from-literal=DATABASE_URL="mysql://user:password@mariadb.asgard.svc:3306/asgard_rl" \
  -n asgard-rl \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 3. Verify Deployment

```bash
# Check pod status
kubectl get pods -n asgard-rl

# Watch pod startup
kubectl logs -f deployment/bifrost -n asgard-rl

# Check service
kubectl get svc -n asgard-rl
```

### 4. Test Service

```bash
# Port forward
kubectl port-forward svc/bifrost 8100:8100 -n asgard-rl

# In another terminal, test the API
curl http://localhost:8100/api/v1/rl/check-deployments
```

## Configuration

### Environment Variables (ConfigMap)

Edit `k8s-manifest.yaml` to customize:

```yaml
data:
  RUST_LOG: "info"                              # Log level
  LISTEN_ADDR: "0.0.0.0:8100"                  # Bind address
  DB_POOL_SIZE: "10"                           # Connection pool
  SCHEDULER_ENABLED: "true"                    # Enable RL scheduler
  DEPLOYMENT_MONITOR_INTERVAL_SECS: "30"       # Health check interval
  DAILY_RL_CYCLE_HOUR_UTC: "2"                 # Cycle trigger time (UTC)
  CANARY_DURATION_HOURS: "2"                   # Canary phase duration
  CANARY_MIN_REQUESTS: "100"                   # Min requests before advancing
```

### Database Credentials (Secret)

Update the secret to match your MariaDB setup:

```bash
kubectl edit secret bifrost-db-secret -n asgard-rl
```

Format: `mysql://user:password@host:port/database`

## Scaling

### Manual Scale

```bash
kubectl scale deployment bifrost --replicas=3 -n asgard-rl
```

### Horizontal Pod Autoscaler (HPA)

HPA is configured in the manifest:
- **Min replicas**: 2
- **Max replicas**: 5
- **CPU trigger**: 70% utilization
- **Memory trigger**: 80% utilization

Monitor autoscaling:

```bash
kubectl get hpa -n asgard-rl --watch
```

## Monitoring

### Check Pod Health

```bash
# Get pod status
kubectl get pods -n asgard-rl -o wide

# Describe pod for events
kubectl describe pod <pod-name> -n asgard-rl

# View logs
kubectl logs <pod-name> -n asgard-rl
kubectl logs -f <pod-name> -n asgard-rl  # Follow logs
```

### Metrics

```bash
# CPU/memory usage
kubectl top pods -n asgard-rl

# Pod resource requests vs actual
kubectl describe pod <pod-name> -n asgard-rl | grep -A10 "Requests"
```

### Network Policy

Bifrost can only communicate with:
- Services in the same namespace
- Dashboard pods (labeled `role: dashboard`)
- DNS (port 53)
- MariaDB (port 3306)
- Mimir API (port 8090)

To debug network issues:

```bash
# Test connectivity from pod
kubectl exec -it <pod-name> -n asgard-rl -- curl http://mariadb.asgard.svc:3306

# Check network policies
kubectl get networkpolicies -n asgard-rl
```

## Troubleshooting

### Pod Won't Start

Check the logs:

```bash
kubectl logs <pod-name> -n asgard-rl
kubectl describe pod <pod-name> -n asgard-rl
```

Common issues:
- **ImagePullBackOff**: Docker image not found in GHCR
- **CrashLoopBackOff**: Database connection failed
- **Pending**: Insufficient resources or network policy blocking

### Database Connection Issues

```bash
# Test database connectivity
kubectl run -it --rm debug --image=mysql:8 --restart=Never -n asgard-rl -- \
  mysql -h mariadb.asgard.svc -u root -p<password> -e "SELECT 1;"
```

### High Memory Usage

```bash
# Check actual memory vs limit
kubectl top pods -n asgard-rl --sort-by=memory

# Increase limit in manifest
spec:
  containers:
    - resources:
        limits:
          memory: 4Gi  # Increase from 2Gi
```

## Updates & Rollouts

### Rolling Update

Update the image tag in the manifest:

```yaml
spec:
  containers:
    - image: ghcr.io/asgard-ai/bifrost:v0.3.1  # New version
```

Then apply:

```bash
kubectl apply -f k8s-manifest.yaml
```

Kubernetes will perform a rolling update (one pod at a time).

### Watch Rollout

```bash
# Check rollout status
kubectl rollout status deployment/bifrost -n asgard-rl

# Rollback if issues
kubectl rollout undo deployment/bifrost -n asgard-rl
```

## Backup & Disaster Recovery

Bifrost doesn't store state locally, so backups focus on:

1. **Database**: Back up MariaDB with the RL tables
2. **Configuration**: Keep the k8s-manifest.yaml and secrets safe
3. **Logs**: Archive logs for audit trails

```bash
# Export current manifests
kubectl get all -n asgard-rl -o yaml > bifrost-backup.yaml

# Export secrets (encrypted)
kubectl get secret bifrost-db-secret -n asgard-rl -o yaml | \
  gpg --encrypt > bifrost-secret-backup.yaml.gpg
```

## Performance Tuning

### Connection Pool Size

For high throughput, increase `DB_POOL_SIZE`:

```bash
kubectl set env deployment/bifrost DB_POOL_SIZE=20 -n asgard-rl
```

### Request Timeout

Increase if queries timeout:

```bash
kubectl set env deployment/bifrost REQUEST_TIMEOUT_SECS=30 -n asgard-rl
```

### Logging Level

Reduce verbose logging for production:

```bash
kubectl set env deployment/bifrost RUST_LOG=warn -n asgard-rl
```

## Security Checklist

- ✅ Non-root user (1000)
- ✅ Read-only root filesystem (except /tmp, /app/cache)
- ✅ No privilege escalation
- ✅ Network policies restrict traffic
- ✅ Resource limits prevent DoS
- ✅ Health checks detect failures
- ✅ Pod disruption budgets ensure availability

To further harden:

```bash
# Add Pod Security Policy
kubectl label namespace asgard-rl pod-security.kubernetes.io/enforce=restricted

# Enable RBAC audit logging
kubectl apply -f - <<EOF
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
  - level: RequestResponse
    verbs: ["create", "update", "patch", "delete"]
    resources: ["secrets", "configmaps"]
EOF
```

## Observability

### Prometheus Metrics

Bifrost exposes metrics at `/metrics`. Add to your Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: bifrost
    static_configs:
      - targets: ['bifrost.asgard-rl.svc:8100']
    metrics_path: '/metrics'
```

### Tracing

Logs use JSON format for structured logging:

```json
{"timestamp":"2026-05-28T02:00:00Z","level":"INFO","message":"RL cycle started","tenant":"asgard_medical"}
```

Integrate with a log aggregator (ELK, Loki, etc.) for full observability.

---

**Deployment Status**: Ready for production  
**Last Updated**: 2026-05-28  
**Version**: 0.3.0+K8s
