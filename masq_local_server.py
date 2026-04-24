#!/usr/bin/env python3
"""
Masq Local Server — Cold-start, zero-idle-VRAM image processor.
Adapted from modal_masq_master.py for local RTX 5060 Ti.

Behavior:
  • Starts instantly, uses ~0 VRAM (models not loaded).
  • First request triggers model init (~5–15s cold start).
  • After IDLE_TIMEOUT seconds of no requests, process exits cleanly.
  • Systemd can restart it, or you start it manually when needed.
"""

import io
import os
import sys
import gc
import time
import threading
from pathlib import Path
from contextlib import asynccontextmanager

import torch
import numpy as np
from PIL import Image
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

# ── Config ─────────────────────────────────────────────────────
IDLE_TIMEOUT = 60          # Seconds of inactivity before suicide
MODEL_DIR = Path("/srv/app-data/masq-local/models")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

MODEL_URLS = {
    "birefnet": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-epoch_244.onnx",
    "realesrgan": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
}

# ── State ──────────────────────────────────────────────────────
_bg_session = None
_upsampler = None
_lock = threading.Lock()
_idle_timer = None
_initialized = False

# ── Model Helpers ──────────────────────────────────────────────
def _ensure_model(name: str, filename: str):
    path = MODEL_DIR / filename
    if path.exists():
        return path
    url = MODEL_URLS[name]
    print(f"[masq-local] Downloading {name} model...", flush=True)
    import urllib.request
    urllib.request.urlretrieve(url, path)
    print(f"[masq-local] Downloaded {path}", flush=True)
    return path

def _setup_models():
    global _bg_session, _upsampler, _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        print("[masq-local] 🧊 COLD START — loading models into VRAM...", flush=True)
        t0 = time.time()

        # Compatibility patch for basicsr
        try:
            import torchvision.transforms.functional as F
            class Fake:
                @staticmethod
                def rgb_to_grayscale(img, num_output_channels=1):
                    return F.rgb_to_grayscale(img, num_output_channels)
            sys.modules["torchvision.transforms.functional_tensor"] = Fake
        except Exception:
            pass

        # 1. BEN-v2 / BiRefNet background removal
        from rembg import new_session
        birefnet_path = _ensure_model("birefnet", "BiRefNet-general-epoch_244.onnx")
        os.environ["U2NET_HOME"] = str(MODEL_DIR)
        _bg_session = new_session("birefnet-general")

        # 2. Real-ESRGAN upscaler
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
        esrgan_path = _ensure_model("realesrgan", "RealESRGAN_x4plus.pth")
        rrdb = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        _upsampler = RealESRGANer(
            scale=4,
            model_path=str(esrgan_path),
            model=rrdb,
            tile=512,
            tile_pad=10,
            pre_pad=0,
            half=True,
            gpu_id=0,
        )

        _initialized = True
        print(f"[masq-local] ✅ Models loaded in {time.time()-t0:.1f}s", flush=True)

def _unload_models():
    global _bg_session, _upsampler, _initialized
    print("[masq-local] 🧹 Unloading models and clearing VRAM...", flush=True)
    _bg_session = None
    _upsampler = None
    _initialized = False
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()
    print("[masq-local] 💀 Exiting to guarantee VRAM release.", flush=True)
    os._exit(0)

def _reset_idle_timer():
    global _idle_timer
    if _idle_timer:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(IDLE_TIMEOUT, _unload_models)
    _idle_timer.daemon = True
    _idle_timer.start()

# ── FastAPI ────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[masq-local] Server up. Idle timeout: {IDLE_TIMEOUT}s. VRAM: 0 on start.")
    yield
    if _idle_timer:
        _idle_timer.cancel()

app = FastAPI(title="Masq Local", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "masq_cloud_ui"

@app.get("/")
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "Masq Local API — POST /process or GET /health"}

@app.get("/health")
async def health():
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
    vram_total = torch.cuda.get_device_properties(0).total_memory // (1024**2) if torch.cuda.is_available() else 0
    return {
        "status": "ok",
        "gpu": gpu,
        "vram_total_mb": vram_total,
        "models_loaded": _initialized,
        "idle_timeout_sec": IDLE_TIMEOUT,
    }

@app.post("/process")
async def process(
    file: UploadFile = File(...),
    task: str = Form("bg"),
    scale: int = Form(4),
):
    _reset_idle_timer()
    _setup_models()  # Cold start happens here on first call

    image_bytes = await file.read()
    t0 = time.time()

    if task == "bg":
        from rembg import remove
        img = Image.open(io.BytesIO(image_bytes))
        output = remove(img, session=_bg_session)
        buf = io.BytesIO()
        output.save(buf, format="PNG", compress_level=0)
        result = buf.getvalue()
    else:
        import cv2
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode == "RGBA":
            arr = np.array(img)
            img_input = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
        else:
            arr = np.array(img.convert("RGB"))
            img_input = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        out_arr, _ = _upsampler.enhance(img_input, outscale=scale)

        if out_arr.shape[2] == 4:
            result_img = Image.fromarray(cv2.cvtColor(out_arr, cv2.COLOR_BGRA2RGBA), mode="RGBA")
        else:
            result_img = Image.fromarray(cv2.cvtColor(out_arr, cv2.COLOR_BGR2RGB), mode="RGB")
        buf = io.BytesIO()
        result_img.save(buf, format="PNG", compress_level=0)
        result = buf.getvalue()

    elapsed = time.time() - t0
    print(f"[masq-local] Processed {task} in {elapsed:.2f}s", flush=True)
    return Response(content=result, media_type="image/png")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8844)
