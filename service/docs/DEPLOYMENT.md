# Akash Deployment Guide

## Overview

This guide covers deploying the image processing service to Akash Network.

**Phase 1 (Current):** CPU-only deployment (~$15-25/month)
**Phase 2 (Future):** GPU upgrade for BEN-v2 (~$96-288/month)

---

## Prerequisites

1. **Akash CLI** installed: https://docs.akash.network/guides/cli
2. **AKT tokens** for deployment (~5-10 AKT to start)
3. **Docker Hub account** for hosting your image
4. **API Keys**: Runware, Kie.ai

---

## Phase 1: CPU Deployment

### Step 1: Build and Push Docker Image

```bash
# Build the image
docker build -t yourusername/img-proc-service:v1.0.0 .

# Push to Docker Hub
docker login
docker push yourusername/img-proc-service:v1.0.0
```

### Step 2: Create Akash SDL

Create `deploy.yaml`:

```yaml
---
version: "2.0"

services:
  img-proc:
    image: yourusername/img-proc-service:v1.0.0
    env:
      - RUNWARE_API_KEY=your_runware_key_here
      - KIE_API_KEY=your_kie_key_here
      - LOG_LEVEL=INFO
      - MAX_CONCURRENT_JOBS=4
    expose:
      - port: 8000
        as: 80
        to:
          - global: true
        http_options:
          max_body_size: 52428800  # 50MB for image uploads

profiles:
  compute:
    img-proc:
      resources:
        cpu:
          units: 2.0
        memory:
          size: 4Gi
        storage:
          size: 5Gi

  placement:
    akash:
      attributes:
        region: us-west
      signedBy:
        anyOf:
          - akash1365yvmc4s7awdyj3n2sav7xfx76adc6dnmlx63
      pricing:
        img-proc:
          denom: uakt
          amount: 1000

deployment:
  img-proc:
    akash:
      profile: img-proc
      count: 1
```

### Step 3: Deploy to Akash

```bash
# Create deployment
akash tx deployment create deploy.yaml --from your-wallet --chain-id akashnet-2

# Wait for bids (usually 30-60 seconds)
akash query market bid list --owner your-address --dseq your-dseq

# Accept a bid
akash tx market lease create --from your-wallet \
  --dseq your-dseq \
  --gseq 1 \
  --oseq 1 \
  --provider provider-address

# Send manifest
akash provider send-manifest deploy.yaml \
  --from your-wallet \
  --provider provider-address \
  --dseq your-dseq

# Get deployment URL
akash provider lease-status \
  --from your-wallet \
  --provider provider-address \
  --dseq your-dseq
```

### Step 4: Verify Deployment

```bash
# Health check
curl https://your-deployment-url.akash.network/health

# Test background removal
curl -X POST https://your-deployment-url.akash.network/remove-background \
  -H "Content-Type: application/json" \
  -d '{"image_url": "https://example.com/test-image.png"}'
```

---

## Resource Breakdown

### Phase 1 (CPU-Only)

| Resource | Allocation | Purpose |
|----------|------------|---------|
| CPU | 2.0 units | FastAPI + Pillow-SIMD + rembg |
| Memory | 4 GB | Image buffers + model loading |
| Storage | 5 GB | OS + Python + rembg models |

**Estimated Cost:** $15-25/month

### Cost Breakdown

| Component | Monthly Cost |
|-----------|-------------|
| 2 vCPU | $8-12 |
| 4GB RAM | $4-6 |
| 5GB Storage | $1-3 |
| Bandwidth (~500GB) | $2-4 |
| **Total** | **$15-25** |

---

## Phase 2: GPU Upgrade (BEN-v2)

When you need BEN-v2 for better background removal quality.

### Modified SDL for GPU

```yaml
---
version: "2.0"

services:
  img-proc-gpu:
    image: yourusername/img-proc-service-gpu:v2.0.0
    env:
      - RUNWARE_API_KEY=your_runware_key_here
      - KIE_API_KEY=your_kie_key_here
      - COMPUTE_BACKEND=gpu
      - LOG_LEVEL=INFO
    expose:
      - port: 8000
        as: 80
        to:
          - global: true
        http_options:
          max_body_size: 52428800

profiles:
  compute:
    img-proc-gpu:
      resources:
        cpu:
          units: 4.0
        memory:
          size: 16Gi
        gpu:
          units: 1
          attributes:
            vendor:
              nvidia:
                - model: rtx4090
                  ram: 24Gi
                - model: rtx3090
                  ram: 24Gi
        storage:
          size: 20Gi  # Extra for BEN-v2 model weights

  placement:
    akash:
      pricing:
        img-proc-gpu:
          denom: uakt
          amount: 5000  # Higher bid for GPU

deployment:
  img-proc-gpu:
    akash:
      profile: img-proc-gpu
      count: 1
```

### GPU Dockerfile

Use `Dockerfile.gpu` instead:

```bash
docker build -f Dockerfile.gpu -t yourusername/img-proc-service-gpu:v2.0.0 .
docker push yourusername/img-proc-service-gpu:v2.0.0
```

### GPU Cost Estimate

| GPU | Hourly | Monthly (24/7) | Monthly (8hr/day) |
|-----|--------|----------------|-------------------|
| RTX 3090 | $0.13-0.40 | $94-288 | $31-96 |
| RTX 4090 | $0.40 | $288 | $96 |

---

## Environment Variables

Store sensitive values securely. Options:

### Option 1: Inline in SDL (Not Recommended for Production)

```yaml
env:
  - RUNWARE_API_KEY=sk_live_xxxxx
```

### Option 2: Akash Secrets (Recommended)

Coming soon in Akash Network updates.

### Option 3: External Secret Manager

Fetch secrets at runtime from Vault, AWS Secrets Manager, etc.

---

## Updating Deployments

### Rolling Update

```bash
# Build new image
docker build -t yourusername/img-proc-service:v1.1.0 .
docker push yourusername/img-proc-service:v1.1.0

# Update SDL with new image tag
# Then update deployment
akash tx deployment update deploy.yaml --from your-wallet --dseq your-dseq
```

### Zero-Downtime Strategy

1. Deploy new version alongside old
2. Test new deployment
3. Switch DNS/load balancer
4. Terminate old deployment

---

## Monitoring

### Health Endpoint

```bash
# Add to cron or monitoring service
curl -f https://your-deployment.akash.network/health || alert "Service down"
```

### Logs

```bash
akash provider lease-logs \
  --from your-wallet \
  --provider provider-address \
  --dseq your-dseq \
  --follow
```

### Metrics (Optional)

Add Prometheus metrics endpoint at `/metrics` for:
- Request count by endpoint
- Processing time histograms
- Model success/failure rates
- Cost tracking

---

## Troubleshooting

### Deployment Won't Start

```bash
# Check lease status
akash provider lease-status --from your-wallet --provider provider --dseq dseq

# Check logs for errors
akash provider lease-logs --from your-wallet --provider provider --dseq dseq
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| No bids received | Price too low | Increase `amount` in pricing |
| Container crashes | OOM | Increase memory allocation |
| Slow responses | CPU throttling | Increase CPU units |
| 413 errors | Upload too large | Increase `max_body_size` |

### Provider Selection Tips

- Choose providers with good uptime history
- Prefer providers in regions close to your users
- Check provider reputation on Akash stats dashboard

---

## Backup & Recovery

### Stateless Design

This service is stateless - all data is processed and returned immediately. No persistent storage backup needed.

### Configuration Backup

Keep your `deploy.yaml` and `.env` files in version control (without secrets).

---

## Cost Optimization

### Right-Sizing

Monitor actual usage and adjust:

```yaml
# Start conservative
cpu: 2.0
memory: 4Gi

# Scale up if needed
cpu: 4.0
memory: 8Gi
```

### Spot-Like Pricing

Set competitive but not excessive pricing:

```yaml
pricing:
  img-proc:
    denom: uakt
    amount: 800  # Lower = cheaper, but fewer providers may bid
```

### Multi-Region (Future)

Deploy to multiple regions for redundancy and lower latency.
