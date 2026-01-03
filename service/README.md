# Image Processing Service

A FastAPI-based image processing service for background removal and upscaling, optimized for DTF (Direct-to-Film) printing workflows.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  VPS Instance (Akash Network)                                   │
│  2 vCPU | 4GB RAM | 5GB Storage | ~$15-25/month                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FastAPI Service                                                │
│  ├── /remove-background (shotgun - returns 5 options)         │
│  ├── /upscale (Lanczos 4x, preserves alpha)                   │
│  └── /process (background removal + upscale pipeline)          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Background Removal Shotgun (5 models)                   │   │
│  │                                                          │   │
│  │  API Models:                                             │   │
│  │  ├── Runware RMBG 2.0      ($0.0006/img) - Best overall │   │
│  │  ├── Runware BiRefNet Port ($0.0006/img) - Portraits    │   │
│  │  └── Kie.ai Recraft BG     ($0.005/img)  - Tough images │   │
│  │                                                          │   │
│  │  Local Models (FREE):                                    │   │
│  │  ├── rembg BiRefNet General - Best on illustrations     │   │
│  │  └── rembg ISNet            - Good on objects           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Upscaling                                               │   │
│  │  └── Lanczos 4x (Pillow-SIMD) - FREE, preserves alpha   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Cost Summary

| Component | Per Image | Per 1,000 Images |
|-----------|-----------|------------------|
| BG Removal (5-model shotgun) | $0.006 | $6.00 |
| Upscaling (Lanczos local) | $0.00 | $0.00 |
| **Total** | **$0.006** | **$6.00** |

VPS hosting: ~$15-25/month fixed

## Features

- **Shotgun Background Removal**: Run 5 models in parallel, return all results for user selection
- **Alpha-Preserving Upscaling**: Lanczos 4x maintains transparency for DTF printing
- **No Size Limits**: Local upscaling handles any image size (unlike API 1MP limits)
- **User Preference Tracking**: Log which model users pick to inform future improvements
- **Async Processing**: Non-blocking API for concurrent requests

## Quick Start

### Local Development

```bash
# Clone and setup
cd service
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run
uvicorn main:app --reload --port 8000
```

### Docker

```bash
docker build -t img-proc-service .
docker run -p 8000:8000 --env-file .env img-proc-service
```

### Akash Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full Akash deployment guide.

## API Endpoints

See [docs/API.md](docs/API.md) for complete API documentation.

### Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/remove-background` | POST | Run 5 BG removal models, return all results |
| `/upscale` | POST | Lanczos 4x upscale (preserves alpha) |
| `/process` | POST | Full pipeline: BG removal + upscale |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `RUNWARE_API_KEY` | Yes | Runware API key for RMBG 2.0 + BiRefNet |
| `KIE_API_KEY` | Yes | Kie.ai API key for Recraft BG |
| `MAX_CONCURRENT_JOBS` | No | Max parallel processing jobs (default: 4) |
| `TEMP_DIR` | No | Temp file directory (default: `/tmp/img-proc`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

## Project Structure

```
service/
├── main.py                 # FastAPI app entry point
├── config.py               # Configuration and environment
├── requirements.txt        # Python dependencies
├── Dockerfile              # Multi-stage Docker build
├── .env.example            # Environment template
│
├── routers/
│   ├── background.py       # /remove-background endpoints
│   ├── upscale.py          # /upscale endpoints
│   └── pipeline.py         # /process pipeline endpoint
│
├── services/
│   ├── shotgun.py          # Orchestrates 5 BG removal models
│   ├── runware_client.py   # Runware WebSocket client
│   ├── kie_client.py       # Kie.ai REST client
│   ├── local_rembg.py      # Local rembg (BiRefNet, ISNet)
│   └── upscaler.py         # Lanczos upscaling with Pillow
│
├── models/
│   └── schemas.py          # Pydantic request/response models
│
├── utils/
│   ├── image_utils.py      # Image loading, saving, format conversion
│   └── tracking.py         # User preference logging
│
└── docs/
    ├── API.md              # API documentation
    ├── DEPLOYMENT.md       # Akash deployment guide
    └── CONFIGURATION.md    # Configuration reference
```

## Phase 2: GPU Upgrade (Future)

When volume justifies it, add BEN-v2 for local GPU background removal:

- **Requirements**: RTX 3090/4090 (24GB VRAM)
- **Cost**: ~$96-288/month on Akash (vs $15-25 for CPU)
- **Benefit**: Best quality BG removal, no per-image API cost

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for GPU upgrade instructions.

## License

MIT
