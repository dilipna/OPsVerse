# OpsVerse on Kubernetes — documented manifests (artifact, not operated)

These manifests show how OpsVerse deploys to Kubernetes. They are a
**portfolio artifact**: reviewed, internally consistent, and explained — but
the operated runtime for this project is Docker Compose (per the plan's
free-tier constraint). They are not applied to a live cluster here.

## Topology

```
Namespace: opsverse
  Deployment/opsverse-api   (2 replicas, HPA 2–6 on CPU)  ─► Service ─► Ingress
  Deployment/opsverse-worker (arq; 1 replica, no Service — pulls from Redis)
  StatefulSet/postgres      (PVC)      StatefulSet/qdrant (PVC)
  Deployment/redis          (ephemeral cache/queue)
  StatefulSet/minio         (PVC)
  Secret/opsverse-secrets   (DB creds, GEMINI_API_KEY, MinIO creds)
  ConfigMap/opsverse-config (non-secret OPSVERSE_* settings)
```

## What each file is

| File | Purpose |
|---|---|
| `namespace.yaml` | the `opsverse` namespace |
| `config.yaml` | ConfigMap (service URLs, model names) + Secret (credentials) |
| `stateful.yaml` | Postgres, Qdrant, MinIO StatefulSets + Services + PVCs |
| `redis.yaml` | Redis Deployment + Service (cache/queue, no persistence) |
| `api.yaml` | API Deployment + Service + HPA + readiness/liveness on `/health/ready` |
| `worker.yaml` | arq worker Deployment (no Service; consumes the Redis queue) |
| `ingress.yaml` | Ingress routing `/` → API (TLS annotation left to the cluster) |

## Production notes (what would change from Compose)

- **Secrets**: `Secret/opsverse-secrets` here is a placeholder; in a real
  cluster it comes from a sealed-secret / external-secrets operator, never
  committed.
- **Storage**: PVCs assume a default StorageClass. Postgres and Qdrant are
  StatefulSets (stable identity + volume); MinIO would be swapped for real S3
  in cloud (one env var — the object-store client is S3-compatible).
- **Readiness gating**: the API's readiness probe hits `/health/ready`, which
  checks Postgres/Redis/Qdrant/MinIO — so the API only receives traffic once
  its dependencies are actually reachable (same check the demo relies on).
- **Scaling**: the API is stateless (all state in the datastores) so the HPA
  scales it freely; the worker is scaled by queue depth, not CPU, and is kept
  at 1 here because embedding is CPU-bound and ordering is not required.

## Apply (illustrative)

```bash
kubectl apply -f infra/k8s/namespace.yaml
kubectl apply -f infra/k8s/config.yaml      # edit secrets first
kubectl apply -f infra/k8s/stateful.yaml infra/k8s/redis.yaml
kubectl apply -f infra/k8s/api.yaml infra/k8s/worker.yaml infra/k8s/ingress.yaml
kubectl -n opsverse rollout status deploy/opsverse-api
```
