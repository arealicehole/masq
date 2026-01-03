# Masq

```text
                              ╭─────────────────────╮
    ███╗   ███╗ █████╗ ███████╗ ██████╗             │
    ████╗ ████║██╔══██╗██╔════╝██╔═══██╗            │
    ██╔████╔██║███████║███████╗██║   ██║  ◈ ◈ ◈    │
    ██║╚██╔╝██║██╔══██║╚════██║██║▄▄ ██║            │
    ██║ ╚═╝ ██║██║  ██║███████║╚██████╔╝            │
    ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝ ╚══▀▀═╝             │
                              ╰─────────────────────╯
         background removal  ·  upscaling  ·  transparency
```

A portable image processing engine with CLI for self-hosting and a Discord Cog for server integration. Background removal via 5-model shotgun + Lanczos upscaling that preserves alpha.

Built by **[Tricon Digital](https://tricondigital.com)**.

---

## Features

- **Core Engine** — Zero-dependency image processing class
- **CLI Tool** — Terminal interface with clean aesthetic
- **Discord Bot** — Full-featured cog with slash commands
- **Library** — Pip installable for your own Python projects
- **Docker** — Container image for deployment
- **Shotgun Mode** — Fire 5 models in parallel, pick the best result

---

## Architecture

```
masq/
├── cogs/
│   └── masq/
│       ├── __init__.py      # Package exports
│       ├── core.py          # The engine
│       └── cog.py           # Discord Cog with /bg and /upscale
├── masq_cli.py              # CLI interface
├── bot.py                   # Standalone Discord bot entry
├── pyproject.toml           # Pip package config
├── requirements.txt         # Dependencies
├── Dockerfile               # Container build
└── service/                 # FastAPI deployment (optional)
```

---

## The 5-Model Shotgun

Background removal fires 5 models in parallel:

| # | Model | Provider | Cost | Notes |
|---|-------|----------|------|-------|
| 1 | RMBG 2.0 | Runware | $0.0006 | Best overall |
| 2 | BiRefNet Portrait | Runware | $0.0006 | Good for people |
| 3 | Recraft BG | Kie.ai | $0.005 | Alternative API |
| 4 | BiRefNet General | Local | FREE | CPU-based |
| 5 | ISNet | Local | FREE | CPU-based |

**Total cost per shotgun: ~$0.006** (if using all API models)

---

## Quick Start

### 1. Get Your API Keys

- **Runware**: Sign up at [runware.ai](https://runware.ai) — $0.0006/image
- **Kie.ai**: Sign up at [kie.ai](https://kie.ai) — $0.005/image
- Local models work without API keys (free but slower)

### 2. Clone & Configure

```bash
git clone https://github.com/arealicehole/masq.git
cd masq
cp .env.example .env
# Edit .env with your API keys
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## CLI Usage

```bash
# Background removal - shotgun (all 5 models)
python masq_cli.py bg photo.png

# Background removal - single model
python masq_cli.py bg photo.png --model runware_rmbg2

# Upscale 4x (preserves transparency)
python masq_cli.py upscale logo.png

# Upscale 8x
python masq_cli.py upscale logo.png --scale 8

# List available models
python masq_cli.py models
```

**Output:**
```text
    ███╗   ███╗ █████╗ ███████╗ ██████╗
    ...
  BACKGROUND REMOVAL
  ─────────────────────
  · Input: photo.png
  · Models: 2 API + 2 Local
  · Mode: Shotgun (4 models)
  ▸ Firing all models in parallel...
  ◈ 4/4 models succeeded

  ◈ 1. RMBG 2.0
      runware · 1823ms · $0.0006
      → bg_photo_162345/1_runware_rmbg2.png
  ...
```

---

## Discord Bot

Full Discord integration with slash commands and model selection UI.

### Setup

1. Create a Discord application at [discord.com/developers](https://discord.com/developers/applications)
2. Add `DISCORD_TOKEN` to your `.env`
3. Invite bot with `applications.commands` and `bot` scopes

### Run

```bash
python bot.py
```

### Commands

| Command | Description |
|---------|-------------|
| `/bg <image>` | Remove background (shotgun - returns all results) |
| `/bg <image> model:<model>` | Remove background with specific model |
| `/upscale <image>` | Upscale 4x with Lanczos |
| `/upscale <image> scale:8` | Upscale 8x |

### Model Selection

When using shotgun mode, the bot returns all successful results with buttons to select the best one. This logs your preference for analytics.

---

## Docker

```bash
# Build
docker build -t masq .

# Run as CLI
docker run --rm -e RUNWARE_API_KEY=your_key \
  -v $(pwd):/data masq \
  bg /data/photo.png

# Run as Discord bot
docker run -d \
  -e DISCORD_TOKEN=your_token \
  -e RUNWARE_API_KEY=your_key \
  -e KIE_API_KEY=your_key \
  masq bot
```

---

## Install as Library (Pip)

Install Masq directly into your own projects:

```bash
pip install git+https://github.com/arealicehole/masq.git
```

Then use it in Python:

```python
from cogs.masq import Masq

async def main():
    masq = Masq(
        runware_key="your_key",
        kie_key="your_key"
    )

    # Shotgun background removal
    result = await masq.remove_background(image_bytes)
    for r in result.successful:
        print(f"{r.model_name}: {len(r.image_bytes)} bytes")

    # Upscale 4x
    upscaled = await masq.upscale(image_bytes, scale=4)
    print(f"Upscaled: {upscaled.upscaled_size}")
```

---

## Tricon Lab Integration

Masq integrates with [Tricon Lab](https://discord.gg/QVAKXAerma) utility bot via the Governor rate limiting system.

Add to your Tricon Lab bot:

```python
# In your bot.py
await bot.load_extension("cogs.masq.cog")
```

Credit costs:
- `/bg` shotgun: 5 credits
- `/bg` single model: 1 credit
- `/upscale`: 1 credit

---

## FastAPI Service

For VPS deployment, see `service/` directory with:
- Full REST API
- Akash deployment SDL
- Docker multi-stage builds
- Health checks

---

## License

MIT License. Free to use, modify, and distribute.

---

<p align="center">
  <strong>Masq</strong> — background removal · upscaling · transparency
</p>
