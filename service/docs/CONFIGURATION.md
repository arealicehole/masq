# Configuration Guide

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `RUNWARE_API_KEY` | Runware API key for RMBG 2.0 and BiRefNet | `rw_live_xxxxx` |
| `KIE_API_KEY` | Kie.ai API key for Recraft BG removal | `kie_xxxxx` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `MAX_CONCURRENT_JOBS` | `4` | Max parallel image processing jobs |
| `TEMP_DIR` | `/tmp/img-proc` | Directory for temporary files |
| `CLEANUP_AFTER_SECONDS` | `300` | Auto-delete temp files after N seconds |
| `REQUEST_TIMEOUT` | `60` | API request timeout in seconds |
| `MAX_IMAGE_SIZE_MB` | `50` | Maximum upload size in MB |

### API-Specific Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `RUNWARE_TIMEOUT` | `120` | Runware WebSocket timeout |
| `RUNWARE_MAX_RETRIES` | `3` | Runware retry attempts |
| `KIE_TIMEOUT` | `120` | Kie.ai polling timeout |
| `KIE_POLL_INTERVAL` | `2` | Kie.ai status poll interval (seconds) |

### Local Model Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `REMBG_MODEL_DIR` | `~/.u2net` | Directory for rembg model weights |
| `BIREFNET_MODEL` | `birefnet-general` | BiRefNet variant to use |
| `ISNET_MODEL` | `isnet-general-use` | ISNet variant to use |
| `USE_GPU` | `false` | Use GPU for local models (Phase 2) |

### Performance Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `UVICORN_WORKERS` | `2` | Number of Uvicorn worker processes |
| `PILLOW_SIMD` | `true` | Use Pillow-SIMD for faster Lanczos |
| `THREAD_POOL_SIZE` | `4` | Thread pool for blocking operations |

---

## Configuration File

Alternative to environment variables, use `config.yaml`:

```yaml
# config.yaml
api:
  runware:
    api_key: ${RUNWARE_API_KEY}  # Can reference env vars
    timeout: 120
    max_retries: 3
  kie:
    api_key: ${KIE_API_KEY}
    timeout: 120
    poll_interval: 2

local_models:
  birefnet:
    model: birefnet-general
    enabled: true
  isnet:
    model: isnet-general-use
    enabled: true

upscaling:
  default_factor: 4
  preserve_alpha: true
  use_simd: true

server:
  host: 0.0.0.0
  port: 8000
  workers: 2
  max_concurrent_jobs: 4

storage:
  temp_dir: /tmp/img-proc
  cleanup_after_seconds: 300
  max_upload_mb: 50

logging:
  level: INFO
  format: json  # or "text"
```

Load with:
```python
from config import load_config
config = load_config("config.yaml")
```

---

## API Keys Setup

### Runware

1. Sign up at https://runware.ai
2. Go to API Keys page
3. Create new key
4. Copy key to `RUNWARE_API_KEY`

**Free tier:** $10 credits to start

**Models used:**
- `runware:110@1` - RMBG 2.0 (~$0.0006/image)
- `runware:112@10` - BiRefNet Portrait (~$0.0006/image)

### Kie.ai

1. Sign up at https://kie.ai
2. Go to API settings
3. Generate API key
4. Copy key to `KIE_API_KEY`

**Pricing:** ~$0.005/image for Recraft BG

---

## Model Configuration

### Background Removal Models

Each model can be enabled/disabled and configured:

```yaml
# models.yaml
background_removal:
  runware_rmbg2:
    enabled: true
    provider: runware
    model_id: "runware:110@1"
    cost_per_image: 0.0006
    timeout: 30
    priority: 1  # Lower = run first

  runware_birefnet_portrait:
    enabled: true
    provider: runware
    model_id: "runware:112@10"
    cost_per_image: 0.0006
    timeout: 30
    priority: 2

  kie_recraft:
    enabled: true
    provider: kie
    model_id: "recraft/remove-background"
    cost_per_image: 0.005
    timeout: 60
    priority: 3

  local_birefnet:
    enabled: true
    provider: local
    model_id: "birefnet-general"
    cost_per_image: 0.0
    timeout: 30
    priority: 4

  local_isnet:
    enabled: true
    provider: local
    model_id: "isnet-general-use"
    cost_per_image: 0.0
    timeout: 20
    priority: 5
```

### Disabling Models

To disable a model, set `enabled: false` or remove from `include_models` in API request.

---

## Logging Configuration

### Log Levels

| Level | Description |
|-------|-------------|
| DEBUG | Detailed debugging info (not for production) |
| INFO | General operational messages |
| WARNING | Something unexpected but not critical |
| ERROR | Something failed |

### Log Format

**JSON (recommended for production):**
```json
{"timestamp": "2025-01-01T12:00:00Z", "level": "INFO", "message": "Processing job abc123", "job_id": "abc123"}
```

**Text (for development):**
```
2025-01-01 12:00:00 INFO Processing job abc123
```

### Log Output

Configure log destination:

```yaml
logging:
  level: INFO
  format: json
  output: stdout  # stdout, file, or both
  file_path: /var/log/img-proc/app.log  # if output includes file
  max_size_mb: 100
  backup_count: 5
```

---

## Security Configuration

### API Key Protection

Never commit API keys to version control:

```bash
# .gitignore
.env
*.env
config.local.yaml
```

### Request Validation

```yaml
security:
  max_upload_size_mb: 50
  allowed_formats:
    - image/png
    - image/jpeg
    - image/webp
  rate_limit:
    requests_per_minute: 60
    burst: 10
```

### CORS (if needed)

```yaml
cors:
  enabled: true
  allow_origins:
    - "https://your-frontend.com"
  allow_methods:
    - GET
    - POST
  allow_headers:
    - Content-Type
    - Authorization
```

---

## Performance Tuning

### For High Throughput

```yaml
server:
  workers: 4  # Match CPU cores
  max_concurrent_jobs: 8

performance:
  pillow_simd: true
  thread_pool_size: 8
  connection_pool_size: 10
```

### For Low Memory

```yaml
server:
  workers: 1
  max_concurrent_jobs: 2

performance:
  thread_pool_size: 2
  cleanup_after_seconds: 60  # Aggressive cleanup
```

### For Large Images

```yaml
storage:
  max_upload_mb: 100
  temp_dir: /mnt/fast-ssd/tmp  # Use fast storage

upscaling:
  chunk_size: 2048  # Process in chunks for very large images
```

---

## Health Check Configuration

```yaml
health:
  endpoint: /health
  include_details: true
  check_runware: true
  check_kie: true
  check_local_models: true
  timeout: 5
```

Response when healthy:
```json
{
  "status": "healthy",
  "checks": {
    "runware": "ok",
    "kie": "ok",
    "local_birefnet": "loaded",
    "local_isnet": "loaded",
    "disk_space": "ok"
  }
}
```
