# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Masq is a portable image processing engine for **background removal** and **upscaling**. It uses a "shotgun" approach that fires 5 AI models in parallel for background removal, returning all results for user selection. Upscaling supports two modes: fast (Lanczos resampling) and premium (Real-ESRGAN AI). Both preserve alpha/transparency (critical for DTF printing workflows). Output is WebP format for smaller file sizes.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI - background removal (shotgun mode - all 5 models)
python masq_cli.py bg image.png

# Run CLI - background removal (single model)
python masq_cli.py bg image.png --model runware_rmbg2

# Run CLI - upscale 4x (default, fast Lanczos)
python masq_cli.py upscale image.png
python masq_cli.py upscale image.png --scale 2

# Run CLI - upscale with Real-ESRGAN (HD mode, slower but better quality)
python masq_cli.py upscale image.png --hd
python masq_cli.py upscale image.png --hd --anime  # for illustrations

# Run CLI - list available models
python masq_cli.py models

# Run Discord bot
python bot.py

# Run FastAPI service (from service/ directory)
cd service
uvicorn main:app --reload --port 8000
```

## Architecture

The project has three deployment modes sharing a common core engine:

```
masq/
├── cogs/masq/
│   ├── core.py          # Core engine: Masq class with all processing logic
│   ├── cog.py           # Discord.py cog with /bg and /upscale commands
│   └── realesrgan.py    # Real-ESRGAN HD upscaler (premium mode)
├── masq_cli.py          # CLI interface (Mardi Gras aesthetic)
├── bot.py               # Standalone Discord bot entry point
└── service/             # FastAPI REST API deployment
    ├── main.py          # FastAPI app entry
    ├── config.py        # Settings from env + config/models.yaml
    ├── routers/
    │   ├── background.py  # /remove-background endpoints
    │   └── upscale.py     # /upscale endpoints
    └── services/
        ├── shotgun.py           # Orchestrates parallel model execution
        └── providers/           # Provider implementations
            ├── base.py          # BaseProvider abstract class
            ├── runware_provider.py
            ├── kie_provider.py
            └── local_provider.py
```

### Core Engine (`cogs/masq/core.py`)

The `Masq` class is the heart of the system:
- `remove_background(image_bytes, models=None)` - Shotgun mode: runs models in parallel via `asyncio.wait()`
- `remove_background_single(image_bytes, model_id)` - Single model execution
- `upscale(image_bytes, scale=4, preserve_alpha=True)` - Fast Lanczos upscaling (WebP output)

### HD Upscaler (`cogs/masq/realesrgan.py`)

Real-ESRGAN AI upscaling for premium mode:
- `upscale_hd(image_bytes, scale=4, model="default")` - AI-based upscaling that reconstructs detail
- Singleton pattern caches model to avoid reload per request
- Runs in thread pool to avoid blocking Discord heartbeat
- Models: `RealESRGAN_x4plus` (general) or `RealESRGAN_x4plus_anime_6B` (illustrations)

### Background Removal Models (5-Model Shotgun)

| Model ID | Name | Provider | Cost |
|----------|------|----------|------|
| `runware_rmbg2` | RMBG 2.0 | Runware API | $0.0006 |
| `runware_birefnet_portrait` | BiRefNet Portrait | Runware API | $0.0006 |
| `kie_recraft` | Recraft BG | Kie.ai API | $0.005 |
| `local_birefnet` | BiRefNet General | Local (rembg) | FREE |
| `local_isnet` | ISNet | Local (rembg) | FREE |

### Provider Pattern

API calls use provider abstraction:
- **Runware**: WebSocket-based via `runware` SDK, returns image URL to fetch
- **Kie.ai**: REST API with CDN upload + polling pattern (createTask -> recordInfo polling)
- **Local**: Uses `rembg` library with pre-loaded sessions, runs in ThreadPoolExecutor

## Configuration

Environment variables (`.env`):
- `RUNWARE_API_KEY` - Enables Runware models
- `KIE_API_KEY` - Enables Kie.ai model
- `DISCORD_TOKEN` - For Discord bot

Model configuration (`service/config/models.yaml`):
- Enable/disable models, set timeouts, costs, priorities
- Shotgun config: parallel execution, total timeout, min successful results

## Key Patterns

1. **Async execution**: All I/O is async. Local models run in `ThreadPoolExecutor` to avoid blocking.

2. **Result dataclasses**: `ModelResult`, `ShotgunResult`, `UpscaleResult` - all have `.to_dict()` for API responses.

3. **Alpha preservation**: Upscaling explicitly handles RGBA mode to preserve transparency for DTF printing.

4. **Singleton services**: FastAPI service uses `get_shotgun_service()` singleton pattern with lazy initialization.

## Discord Bot Commands

**`/bg <image> [model]`** - Remove background
- No model specified: Runs all 5 models in parallel (shotgun), returns all results
- With model: Runs single specified model

**`/upscale <image> [scale] [mode]`** - Upscale image
- `scale`: 2x or 4x (default: 4x)
- `mode`:
  - `fast` (default): Instant Lanczos resampling
  - `premium`: Real-ESRGAN AI (~1-2 min on CPU, better quality for degraded images)

Output is WebP format (smaller files, supports alpha). Discord limit is 25MB.

## Discord Bot Integration

The cog (`cogs/masq/cog.py`) integrates with Tricon Lab's Governor rate limiting system:
- Credit costs defined in `CREDIT_COSTS` dict
- Selection tracking: `ModelSelectView` lets users pick best result, logs preference for analytics
