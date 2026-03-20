import modal
import io
import os
import sys
from pathlib import Path

# 1. Define the environment with EVERYTHING baked in (BEN-v2 + ERSGAN)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0", "libmagic1", "wget")
    .pip_install(
        "fastapi[standard]",
        "torch",
        "torchvision",
        "rembg[gpu]",
        "onnxruntime-gpu",
        "pillow",
        "huggingface_hub",
        "realesrgan",
        "basicsr"
    )
    # Bake all models into the image during free build
    .run_commands(
        "mkdir -p /root/.u2net",
        # BEN-v2 Model
        "wget https://github.com/danielgatis/rembg/releases/download/v0.0.0/BiRefNet-general-epoch_244.onnx -O /root/.u2net/birefnet-general.onnx",
        # Real-ESRGAN Model
        "wget https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth -O /root/.u2net/RealESRGAN_x4plus.pth"
    )
)

app = modal.App("masq-master")

@app.cls(
    image=image,
    gpu="L40S",           # Fastest for both BG and Upscale
    memory=16384,        # 16GB is enough for both
    timeout=600
)
class MasqEngine:
    @modal.enter()
    def setup(self):
        """Initialize both sessions once container starts."""
        # 1. Apply compatibility patch for basicsr
        try:
            import torchvision.transforms.functional as F
            class Fake:
                @staticmethod
                def rgb_to_grayscale(img, num_output_channels=1):
                    return F.rgb_to_grayscale(img, num_output_channels)
            sys.modules['torchvision.transforms.functional_tensor'] = Fake
        except Exception: pass

        # 2. Start rembg session
        from rembg import new_session
        self.bg_session = new_session("birefnet-general")

        # 3. Start ERSGAN session
        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet
        
        model_path = "/root/.u2net/RealESRGAN_x4plus.pth"
        rrdb_model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        self.upsampler = RealESRGANer(
            scale=4,
            model_path=model_path,
            model=rrdb_model,
            tile=512,
            tile_pad=10,
            pre_pad=0,
            half=True,
            gpu_id=0
        )

    @modal.method()
    async def remove_bg(self, image_bytes: bytes) -> bytes:
        from rembg import remove
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        output = remove(img, session=self.bg_session)
        buf = io.BytesIO()
        output.save(buf, format="PNG", compress_level=0)
        return buf.getvalue()

    @modal.method()
    async def upscale(self, image_bytes: bytes, scale: int = 4) -> bytes:
        import cv2
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        
        if img.mode == "RGBA":
            img_array = np.array(img)
            img_input = cv2.cvtColor(img_array, cv2.COLOR_RGBA2BGRA)
        else:
            img_array = np.array(img.convert("RGB"))
            img_input = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)

        output, _ = self.upsampler.enhance(img_input, outscale=scale)

        if output.shape[2] == 4:
            result = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGRA2RGBA), mode="RGBA")
        else:
            result = Image.fromarray(cv2.cvtColor(output, cv2.COLOR_BGR2RGB), mode="RGB")

        buf = io.BytesIO()
        result.save(buf, format="PNG", compress_level=0)
        return buf.getvalue()

# ── Web API for Masq Cloud UI ──────────────────────────────────────────
from fastapi import Request, Response
from fastapi.responses import JSONResponse

@app.function(image=image)
@modal.asgi_app()
def web():
    from fastapi import FastAPI, UploadFile, File, Form
    from fastapi.middleware.cors import CORSMiddleware

    api = FastAPI(title="Masq Master API")
    api.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @api.post("/process")
    async def process(
        file: UploadFile = File(...),
        task: str = Form("bg"),
        scale: int = Form(4),
    ):
        image_bytes = await file.read()
        engine = MasqEngine()

        if task == "bg":
            result = await engine.remove_bg.remote.aio(image_bytes)
        else:
            result = await engine.upscale.remote.aio(image_bytes, scale)

        return Response(content=result, media_type="image/png")

    @api.get("/health")
    async def health():
        return {"status": "ok", "engines": ["benv2", "realesrgan"]}

    return api
