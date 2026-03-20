# Masq Master: Cloud Architecture

## Overview

Masq Master is a **dual-engine GPU image processor** deployed on [Modal](https://modal.com). A single L40S container runs both AI models back-to-back, keeping the GPU warm between calls to minimize cold starts and cost.

```
┌──────────────────────────────────────────────────┐
│              Modal Container (L40S)               │
│                  16 GB Memory                     │
│                                                   │
│  ┌─────────────────┐    ┌──────────────────────┐  │
│  │    Engine 1      │    │      Engine 2         │  │
│  │    BEN-v2        │    │    Real-ESRGAN        │  │
│  │  (BG Removal)    │───▶│    (Upscaling)        │  │
│  │                  │    │                       │  │
│  │  birefnet-general│    │  RealESRGAN_x4plus    │  │
│  │  via rembg       │    │  via realesrgan       │  │
│  └─────────────────┘    └──────────────────────┘  │
│                                                   │
│  Web Endpoint: POST /process                      │
└──────────────────────────────────────────────────┘
         ▲                          │
         │  image + task + scale    │  processed PNG
         │                          ▼
┌──────────────────────────────────────────────────┐
│              Masq Cloud UI                        │
│  (Static HTML/CSS/JS — browser-based)             │
│                                                   │
│  • Drag & drop batch upload                       │
│  • Per-image task selection (BG / Upscale)         │
│  • Progress tracking + cost estimation            │
│  • Results gallery with download                  │
└──────────────────────────────────────────────────┘
```

---

## Dual Engine Design

### Engine 1: BEN-v2 (Background Removal)

- **Model:** BiRefNet-general-epoch_244.onnx (branded as BEN-v2)
- **Library:** `rembg` with `birefnet-general` session
- **Input:** Raw image bytes (PNG/JPG/JPEG/WebP)
- **Output:** PNG with transparent background (alpha channel)
- **Method:** `MasqEngine.remove_bg(image_bytes) → bytes`

### Engine 2: Real-ESRGAN (Upscaling)

- **Model:** RealESRGAN_x4plus.pth
- **Library:** `realesrgan` + `basicsr`
- **Input:** Image bytes (supports RGBA for transparency preservation)
- **Output:** Upscaled PNG (2x–8x)
- **Config:** tile=512, tile_pad=10, half precision (FP16)
- **Method:** `MasqEngine.upscale(image_bytes, scale) → bytes`

### Why One Container?

Running both models in a single container means:
1. **No cold start between passes** — BG removal → upscale runs instantly on the same warm GPU
2. **Shared GPU memory** — both models fit comfortably in L40S VRAM
3. **Lower cost** — one container billing period covers both operations
4. **Simpler deployment** — single `modal deploy` command

---

## Container Configuration

```python
@app.cls(
    image=image,
    gpu="L40S",        # NVIDIA L40S — fast for both inference types
    memory=16384,      # 16 GB system RAM
    timeout=600        # 10 min max per request
)
```

### Baked Image

Both models are downloaded at **image build time** (free on Modal), so cold starts only pay for model loading into GPU memory, not download time:

```python
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "wget")
    .pip_install("torch", "torchvision", "rembg[gpu]", ...)
    .run_commands(
        "wget BiRefNet-general-epoch_244.onnx ...",  # BEN-v2
        "wget RealESRGAN_x4plus.pth ..."              # ESRGAN
    )
)
```

---

## API Contract

### `POST /process`

Process a single image with either engine.

**Request:** `multipart/form-data`

| Field    | Type   | Required | Default | Description                    |
|----------|--------|----------|---------|--------------------------------|
| `file`   | File   | Yes      | —       | Image file (PNG/JPG/JPEG/WebP) |
| `task`   | string | No       | `bg`    | `bg` or `upscale`              |
| `scale`  | int    | No       | `4`     | Upscale factor (2–8)           |

**Response:** `image/png` — processed image bytes

**Errors:** JSON `{ "error": "message" }`

---

## Cost Model

| Operation | Approx Time | Approx Cost |
|-----------|-------------|-------------|
| Container cold start | ~15–30s | ~$0.02–0.04 |
| BG removal (per image) | ~2–4s | ~$0.003–0.006 |
| Upscale 2x (per image) | ~3–5s | ~$0.004–0.007 |
| Upscale 4x (per image) | ~5–8s | ~$0.007–0.012 |

**Batch estimate (18 shirts, BG + 2x upscale each):**
- First image: ~$0.07 (includes cold start)
- Each additional: ~$0.01
- **Total: ~$0.24**

Container stays warm between sequential calls, so batch processing is heavily discounted after the first image.

---

## Deployment

```bash
# Deploy the dual engine to Modal
modal deploy modal_masq_master.py

# Verify deployment
modal app list   # Should show "masq-master"

# Test with CLI
python batch_test_shirts.py
```

### Web UI

Open `masq_cloud_ui/index.html` in any browser. Set the Modal endpoint URL in Settings. No server or build step required.

---

## File Map

| File | Purpose |
|------|---------|
| `modal_masq_master.py` | Dual-engine Modal app (BEN-v2 + ESRGAN) |
| `benv2_modal.py` | Standalone BEN-v2 Modal app (BG only) |
| `ersgan_modal.py` | Standalone ESRGAN Modal app (upscale only) |
| `gui_masq.py` | Streamlit prototype (legacy) |
| `masq_cloud_ui/` | Production web UI (HTML/CSS/JS) |
| `batch_test_shirts.py` | CLI batch processing script |
