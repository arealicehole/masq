# API Documentation

## Base URL

```
http://localhost:8000  (development)
https://your-akash-deployment.com  (production)
```

## Authentication

Currently no authentication required. Add API key middleware for production.

---

## Endpoints

### Health Check

```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "services": {
    "runware": "connected",
    "kie": "available",
    "local_rembg": "loaded"
  }
}
```

---

### Remove Background (Shotgun)

Run 5 background removal models in parallel and return all results.

```
POST /remove-background
```

**Request Body:**
```json
{
  "image": "base64_encoded_image_data",
  "image_url": "https://example.com/image.png",
  "output_format": "png",
  "include_models": ["all"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `image` | string | No* | Base64-encoded image data |
| `image_url` | string | No* | URL to fetch image from |
| `output_format` | string | No | Output format: `png` (default), `webp` |
| `include_models` | array | No | Models to run: `all` (default), or specific model IDs |

*One of `image` or `image_url` is required.

**Available Model IDs:**
- `runware_rmbg2` - Runware RMBG 2.0
- `runware_birefnet_portrait` - Runware BiRefNet Portrait
- `kie_recraft` - Kie.ai Recraft BG
- `local_birefnet` - Local rembg BiRefNet General
- `local_isnet` - Local rembg ISNet

**Response:**
```json
{
  "job_id": "uuid-v4-string",
  "status": "completed",
  "processing_time_ms": 3250,
  "results": [
    {
      "model_id": "runware_rmbg2",
      "model_name": "Runware RMBG 2.0",
      "status": "success",
      "image_base64": "base64_encoded_result",
      "image_url": "https://temp-storage.com/result1.png",
      "processing_time_ms": 1200,
      "cost_usd": 0.0006
    },
    {
      "model_id": "runware_birefnet_portrait",
      "model_name": "Runware BiRefNet Portrait",
      "status": "success",
      "image_base64": "base64_encoded_result",
      "image_url": "https://temp-storage.com/result2.png",
      "processing_time_ms": 1150,
      "cost_usd": 0.0006
    },
    {
      "model_id": "kie_recraft",
      "model_name": "Kie.ai Recraft BG",
      "status": "success",
      "image_base64": "base64_encoded_result",
      "image_url": "https://temp-storage.com/result3.png",
      "processing_time_ms": 2800,
      "cost_usd": 0.005
    },
    {
      "model_id": "local_birefnet",
      "model_name": "Local BiRefNet General",
      "status": "success",
      "image_base64": "base64_encoded_result",
      "image_url": null,
      "processing_time_ms": 2500,
      "cost_usd": 0.0
    },
    {
      "model_id": "local_isnet",
      "model_name": "Local ISNet",
      "status": "success",
      "image_base64": "base64_encoded_result",
      "image_url": null,
      "processing_time_ms": 1800,
      "cost_usd": 0.0
    }
  ],
  "total_cost_usd": 0.0062
}
```

**Error Response:**
```json
{
  "job_id": "uuid-v4-string",
  "status": "partial",
  "results": [
    {
      "model_id": "runware_rmbg2",
      "status": "error",
      "error": "API timeout after 30s",
      "processing_time_ms": 30000,
      "cost_usd": 0.0
    }
  ]
}
```

---

### Upscale Image

Upscale image using Lanczos 4x (preserves alpha/transparency).

```
POST /upscale
```

**Request Body:**
```json
{
  "image": "base64_encoded_image_data",
  "image_url": "https://example.com/image.png",
  "scale_factor": 4,
  "output_format": "png",
  "preserve_alpha": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | string | No* | - | Base64-encoded image data |
| `image_url` | string | No* | - | URL to fetch image from |
| `scale_factor` | integer | No | 4 | Upscale factor: 2 or 4 |
| `output_format` | string | No | `png` | Output format: `png`, `webp` |
| `preserve_alpha` | boolean | No | true | Preserve transparency |

*One of `image` or `image_url` is required.

**Response:**
```json
{
  "job_id": "uuid-v4-string",
  "status": "completed",
  "input_dimensions": {
    "width": 512,
    "height": 768
  },
  "output_dimensions": {
    "width": 2048,
    "height": 3072
  },
  "scale_factor": 4,
  "alpha_preserved": true,
  "processing_time_ms": 850,
  "image_base64": "base64_encoded_result",
  "cost_usd": 0.0
}
```

---

### Full Pipeline (Background Removal + Upscale)

Run background removal shotgun, then upscale all results.

```
POST /process
```

**Request Body:**
```json
{
  "image": "base64_encoded_image_data",
  "image_url": "https://example.com/image.png",
  "bg_models": ["all"],
  "upscale_factor": 4,
  "output_format": "png"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `image` | string | No* | - | Base64-encoded image data |
| `image_url` | string | No* | - | URL to fetch image from |
| `bg_models` | array | No | `["all"]` | BG models to run |
| `upscale_factor` | integer | No | 4 | Upscale factor: 2 or 4 |
| `output_format` | string | No | `png` | Output: `png`, `webp` |

**Response:**
```json
{
  "job_id": "uuid-v4-string",
  "status": "completed",
  "processing_time_ms": 5200,
  "results": [
    {
      "model_id": "runware_rmbg2",
      "model_name": "Runware RMBG 2.0",
      "bg_removal_status": "success",
      "upscale_status": "success",
      "input_dimensions": {"width": 512, "height": 768},
      "output_dimensions": {"width": 2048, "height": 3072},
      "image_base64": "base64_encoded_final_result",
      "processing_time_ms": 2050,
      "cost_usd": 0.0006
    }
  ],
  "total_cost_usd": 0.0062
}
```

---

### Log User Selection (Preference Tracking)

Track which model the user selected (for future optimization).

```
POST /log-selection
```

**Request Body:**
```json
{
  "job_id": "uuid-from-previous-request",
  "selected_model_id": "runware_rmbg2",
  "image_category": "illustration",
  "notes": "cleanest edges"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `job_id` | string | Yes | Job ID from BG removal request |
| `selected_model_id` | string | Yes | Model ID user chose |
| `image_category` | string | No | Optional category tag |
| `notes` | string | No | Optional user notes |

**Response:**
```json
{
  "status": "logged",
  "selection_id": "uuid-v4-string"
}
```

---

## Error Codes

| HTTP Code | Error Type | Description |
|-----------|------------|-------------|
| 400 | `validation_error` | Invalid request body |
| 400 | `missing_image` | Neither `image` nor `image_url` provided |
| 400 | `invalid_format` | Unsupported image format |
| 413 | `image_too_large` | Image exceeds 50MB limit |
| 422 | `processing_error` | All models failed |
| 500 | `internal_error` | Server error |
| 503 | `service_unavailable` | External API unavailable |

**Error Response Format:**
```json
{
  "error": {
    "type": "validation_error",
    "message": "Invalid image format. Supported: PNG, JPG, WEBP",
    "details": {
      "field": "image",
      "received": "image/gif"
    }
  }
}
```

---

## Rate Limits

| Tier | Requests/min | Concurrent Jobs |
|------|--------------|-----------------|
| Default | 60 | 4 |

Rate limit headers included in response:
```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 58
X-RateLimit-Reset: 1704067200
```

---

## Webhooks (Optional)

For async processing, provide a webhook URL:

```json
{
  "image_url": "https://example.com/image.png",
  "webhook_url": "https://your-server.com/webhook",
  "webhook_secret": "your-secret-for-signature"
}
```

Webhook payload:
```json
{
  "event": "job_completed",
  "job_id": "uuid-v4-string",
  "results": [...],
  "signature": "hmac-sha256-signature"
}
```
