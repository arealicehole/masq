import modal
import os
from pathlib import Path
import time

# Config
INPUT_DIR = r"C:\Users\figon\OneDrive\mockup templates\Shirts"
OUTPUT_DIR = Path(INPUT_DIR) / "processed"

def run_batch():
    # 1. Connect to the Master Engine
    try:
        engine = modal.Cls.from_name("masq-master", "MasqEngine")()
    except Exception as e:
        print(f"❌ Error: Could not find 'masq-master'. Did you run 'modal deploy modal_masq_master.py'?")
        return

    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Get list of images
    extensions = {'.png', '.jpg', '.jpeg', '.webp'}
    files = [f for f in Path(INPUT_DIR).glob('*') if f.suffix.lower() in extensions]
    
    print(f"🚀 Starting Batch: {len(files)} shirts (Total 36 jobs: BG + Upscale)")
    start_time = time.time()

    for idx, file_path in enumerate(files):
        print(f"--- [{idx+1}/{len(files)}] Processing: {file_path.name} ---")
        
        with open(file_path, "rb") as f:
            original_bytes = f.read()

        # PASS 1: Remove Background
        t1 = time.time()
        print("  ✂️ Removing background...")
        no_bg_bytes = engine.remove_bg.remote(original_bytes)
        
        # PASS 2: Upscale 2x
        print("  🎨 Upscaling 2x...")
        final_bytes = engine.upscale.remote(no_bg_bytes, scale=2)
        t2 = time.time()

        # Save Final Result
        out_name = f"{file_path.stem}_no_bg_2x.png"
        with open(OUTPUT_DIR / out_name, "wb") as f:
            f.write(final_bytes)
        
        print(f"  ✅ Finished in {t2-t1:.1f}s")

    total_duration = time.time() - start_time
    print(f"\n🎉 BATCH COMPLETE!")
    print(f"Total time: {total_duration:.1f}s")
    print(f"Results saved to: {OUTPUT_DIR}")
    print(f"Approx Modal Cost: ${(0.07 + (0.01 * (len(files)*2-1))):.2f}")

if __name__ == "__main__":
    run_batch()
