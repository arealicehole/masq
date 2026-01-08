#!/usr/bin/env python3
"""
Masq CLI
Background removal & upscaling from your terminal.

Usage:
    # Background removal (shotgun - all models)
    python masq_cli.py bg image.png

    # Background removal (single model)
    python masq_cli.py bg image.png --model runware_rmbg2

    # Upscale 4x
    python masq_cli.py upscale image.png

    # Upscale with custom scale
    python masq_cli.py upscale image.png --scale 8
"""

import argparse
import asyncio
import io
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from cogs.masq import Masq, MODELS, DEFAULT_SHOTGUN_MODELS

# ==================== Masquerade Aesthetic ====================

BANNER = r"""
    â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
    â•‘                                                               â•‘
    â•‘         â–ˆâ–ˆâ–ˆâ•—   â–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•—                â•‘
    â•‘         â–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•— â–ˆâ–ˆâ•”â•â•â•â•â• â–ˆâ–ˆâ•”â•â•â•â–ˆâ–ˆâ•—               â•‘
    â•‘  âšœ â—†   â–ˆâ–ˆâ•”â–ˆâ–ˆâ–ˆâ–ˆâ•”â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘ â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•— â–ˆâ–ˆâ•‘   â–ˆâ–ˆâ•‘   â—† âšœ        â•‘
    â•‘         â–ˆâ–ˆâ•‘â•šâ–ˆâ–ˆâ•”â•â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•”â•â•â–ˆâ–ˆâ•‘ â•šâ•â•â•â•â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•‘â–„â–„ â–ˆâ–ˆâ•‘               â•‘
    â•‘         â–ˆâ–ˆâ•‘ â•šâ•â• â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ•‘  â–ˆâ–ˆâ•‘ â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•‘ â•šâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ•”â•               â•‘
    â•‘         â•šâ•â•     â•šâ•â• â•šâ•â•  â•šâ•â• â•šâ•â•â•â•â•â•â•  â•šâ•â•â–€â–€â•â•                â•‘
    â•‘                                                               â•‘
    â•‘        â•â•â•â•â•â• Rue Royale, 1889 Â· Le Bal des Ombres â•â•â•â•â•â•     â•‘
    â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
"""

# ANSI Colors - Mardi Gras palette
class C:
    PURPLE = "\033[38;5;129m"    # Royal purple
    GOLD = "\033[38;5;220m"      # Mardi Gras gold
    GREEN = "\033[38;5;34m"      # Mardi Gras green
    WHITE = "\033[97m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


def print_banner():
    print(f"{C.PURPLE}{BANNER}{C.RESET}")


def print_status(msg: str, symbol: str = "â”‚"):
    print(f"  {C.DIM}{symbol}{C.RESET} {msg}")


def print_success(msg: str):
    print(f"  {C.GOLD}â—†{C.RESET} {msg}")


def print_error(msg: str):
    print(f"  {C.PURPLE}âœ—{C.RESET} {msg}")


def print_info(msg: str):
    print(f"  {C.PURPLE}âšœ{C.RESET} {msg}")


def print_header(msg: str):
    print(f"\n  {C.BOLD}{C.GOLD}{msg}{C.RESET}")
    print(f"  {C.DIM}{'â•' * len(msg)}{C.RESET}")


def print_result_box(title: str, items: list[tuple[str, str]]):
    """Print a styled result box."""
    width = max(len(title), max(len(k) + len(v) + 2 for k, v in items)) + 4
    print(f"\n  {C.PURPLE}â•”{'â•' * width}â•—{C.RESET}")
    print(f"  {C.PURPLE}â•‘{C.RESET} {C.BOLD}{C.GOLD}{title}{' ' * (width - len(title) - 1)}{C.PURPLE}â•‘{C.RESET}")
    print(f"  {C.PURPLE}â• {'â•' * width}â•£{C.RESET}")
    for key, value in items:
        line = f"{key}: {value}"
        padding = width - len(line) - 1
        print(f"  {C.PURPLE}â•‘{C.RESET} {C.DIM}{key}:{C.RESET} {C.GOLD}{value}{' ' * padding}{C.PURPLE}â•‘{C.RESET}")
    print(f"  {C.PURPLE}â•š{'â•' * width}â•{C.RESET}")


# ==================== Scene Intros ====================

def scene_bg_solo():
    """Scene: Private game in the back room."""
    print(f"\n  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}De ballroom buzzes wit' masks an' secrets...{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}A stranger in velvet catches your eye.{C.RESET}")
    print(f"  {C.GOLD}â—†{C.RESET} {C.BOLD}\"Jus' you an' me tonight, mon ami. One card.{C.RESET}")
    print(f"    {C.BOLD}Let's see what fate has in store...\"{C.RESET}")
    print(f"  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}\n")


def scene_bg_grand():
    """Scene: The high-stakes game in the back room."""
    print(f"\n  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}Chandeliers flicker. De music stops.{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}Someone whispers: \"Dey startin' Le Grand Jeu...\"{C.RESET}")
    print(f"  {C.GOLD}â—†{C.RESET} {C.BOLD}\"Gather 'round, chers. Every player at de table.{C.RESET}")
    print(f"    {C.BOLD}Tonight, we see who's got de magic touch...\"{C.RESET}")
    print(f"  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}\n")


def scene_upscale():
    """Scene: Gambit charges up."""
    print(f"\n  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}De crowd parts. A card appears between gloved fingers.{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}It begins to glow... purple, den gold...{C.RESET}")
    print(f"  {C.GOLD}â—†{C.RESET} {C.BOLD}\"You want it bigger, non? Watch dis, cher.{C.RESET}")
    print(f"    {C.BOLD}Remy make t'ings... magnifique.\"{C.RESET}")
    print(f"  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}\n")


def scene_models():
    """Scene: Surveying the guests."""
    print(f"\n  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}You step t'rough de iron gates onto Rue Royale.{C.RESET}")
    print(f"  {C.PURPLE}âšœ{C.RESET} {C.DIM}Masks everywhere. Silk. Secrets. Danger.{C.RESET}")
    print(f"  {C.GOLD}â—†{C.RESET} {C.BOLD}\"Lemme show you who's at de ball tonight, mon ami.{C.RESET}")
    print(f"    {C.BOLD}Some got power... some got style... some got bot'.\"{C.RESET}")
    print(f"  {C.DIM}â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€{C.RESET}\n")


# ==================== Commands ====================

async def cmd_bg(args):
    """Background removal command."""
    input_path = Path(args.input)

    if not input_path.exists():
        print_error(f"File not found: {input_path}")
        return 1

    # Load API keys
    runware_key = os.getenv("RUNWARE_API_KEY")
    kie_key = os.getenv("KIE_API_KEY")
    masq = Masq(runware_key=runware_key, kie_key=kie_key)

    # Read image
    image_bytes = input_path.read_bytes()

    try:
        if args.model:
            # Single model mode - set the scene
            scene_bg_solo()
            print_status(f"De card: {C.GOLD}{args.model}{C.RESET}")
            print_status(f"De mark: {C.DIM}{input_path.name}{C.RESET} ({len(image_bytes) / 1024:.1f} KB)")
            print_info("Playin' de hand...")

            result = await masq.remove_background_single(image_bytes, args.model)

            if not result.is_success:
                print_error(f"De card folds: {result.error}")
                return 1

            # Save output
            output_path = args.output or f"bg_{input_path.stem}_{args.model}.png"
            Path(output_path).write_bytes(result.image_bytes)

            print_success("Dat's a winnin' hand!")
            print_result_box("RÃ‰VÃ‰LÃ‰", [
                ("Model", result.model_name),
                ("Time", f"{result.processing_time_ms:.0f}ms"),
                ("Cost", f"${result.cost:.4f}"),
                ("Output", f"file:///{Path(output_path).absolute().as_posix()}")
            ])

        else:
            # Shotgun mode - set the scene
            models = args.models.split(",") if args.models else None
            model_count = len(models) if models else len(DEFAULT_SHOTGUN_MODELS)

            available = masq.get_available_models()
            api_count = sum(1 for m in available if m["available"] and m["provider"] != "local")
            local_count = sum(1 for m in available if m["available"] and m["provider"] == "local")

            scene_bg_grand()
            print_status(f"De table: {C.GOLD}{api_count} high rollers{C.RESET} + {C.GREEN}{local_count} locals{C.RESET}")
            print_status(f"De stakes: {C.DIM}{input_path.name}{C.RESET} ({len(image_bytes) / 1024:.1f} KB)")
            print_info(f"Dealin' to {model_count} players...")

            result = await masq.remove_background(image_bytes, models)

            if not result.successful:
                print_error("De house wins dis round, cher...")
                for r in result.results:
                    if r.error:
                        print_status(f"{r.model_name}: {r.error}", "âœ—")
                return 1

            # Save all successful outputs
            output_dir = Path(args.output_dir or f"bg_{input_path.stem}_{datetime.now().strftime('%H%M%S')}")
            output_dir.mkdir(exist_ok=True)

            print_success(f"VoilÃ ! {len(result.successful)}/{len(result.results)} came t'rough")
            print()

            for i, r in enumerate(result.successful):
                out_file = output_dir / f"{i+1}_{r.model_id}.png"
                out_file.write_bytes(r.image_bytes)
                status = f"{C.GOLD}â—†{C.RESET}" if r.is_success else f"{C.PURPLE}âœ—{C.RESET}"
                print(f"  {status} {C.BOLD}{i+1}. {r.model_name}{C.RESET}")
                print(f"      {C.DIM}{r.provider} Â· {r.processing_time_ms:.0f}ms Â· ${r.cost:.4f}{C.RESET}")
                print(f"      {C.PURPLE}âšœ{C.RESET} {out_file}")

            print_result_box("LE BAL", [
                ("Total Time", f"{result.total_time_ms:.0f}ms"),
                ("Total Cost", f"${result.total_cost:.4f}"),
                ("Output Dir", f"file:///{Path(output_dir).absolute().as_posix()}")
            ])

    finally:
        await masq.close()

    return 0


async def cmd_upscale(args):
    """Upscale command."""
    input_path = Path(args.input)

    if not input_path.exists():
        print_error(f"File not found: {input_path}")
        return 1

    image_bytes = input_path.read_bytes()

    scene_upscale()
    print_status(f"De target: {C.DIM}{input_path.name}{C.RESET} ({len(image_bytes) / 1024:.1f} KB)")
    print_status(f"De power: {C.GOLD}{args.scale}x{C.RESET}")

    if args.hd:
        # HD Mode - Real-ESRGAN (slower but reconstructs detail)
        from cogs.masq.realesrgan import upscale_hd

        model = "anime" if args.anime else "default"
        print_status(f"De mode: {C.GOLD}HD{C.RESET} (Real-ESRGAN {model})")
        print_info("Dis gonna take a minute, cher... Real magic takes time.")

        result = await upscale_hd(
            image_bytes,
            scale=args.scale,
            model=model,
            tile=args.tile
        )

        if not result.success:
            print_error(f"Failed: {result.error}")
            return 1

        # Save output
        output_path = args.output or f"upscaled_hd_{args.scale}x_{input_path.stem}.png"
        Path(output_path).write_bytes(result.image_bytes)

        print_success("Boom! Dat's de real magic, cher!")
        print_result_box("MAGNIFIQUE HD", [
            ("Original", f"{result.original_size[0]}x{result.original_size[1]}"),
            ("Upscaled", f"{result.upscaled_size[0]}x{result.upscaled_size[1]}"),
            ("Scale", f"{result.scale_factor}x"),
            ("Model", result.model_used),
            ("Alpha", "Preserved" if result.has_alpha else "Non"),
            ("Time", f"{result.processing_time_ms/1000:.1f}s"),
            ("Output", f"file:///{Path(output_path).absolute().as_posix()}")
        ])
    else:
        # Standard Mode - Lanczos (fast)
        masq = Masq()
        print_info("Chargin' up...")

        result = await masq.upscale(
            image_bytes,
            scale=args.scale,
            preserve_alpha=not args.no_alpha
        )

        if not result.success:
            print_error(f"Failed: {result.error}")
            return 1

        # Save output
        output_path = args.output or f"upscaled_{args.scale}x_{input_path.stem}.png"
        Path(output_path).write_bytes(result.image_bytes)

        print_success("Boom! Bigger dan life, cher!")
        print_result_box("MAGNIFIQUE", [
            ("Original", f"{result.original_size[0]}x{result.original_size[1]}"),
            ("Upscaled", f"{result.upscaled_size[0]}x{result.upscaled_size[1]}"),
            ("Scale", f"{result.scale_factor}x"),
            ("Alpha", "Preserved" if result.has_alpha else "Non"),
            ("Time", f"{result.processing_time_ms:.0f}ms"),
            ("Output", f"file:///{Path(output_path).absolute().as_posix()}")
        ])

    return 0


async def cmd_models(args):
    """List available models."""
    runware_key = os.getenv("RUNWARE_API_KEY")
    kie_key = os.getenv("KIE_API_KEY")

    masq = Masq(runware_key=runware_key, kie_key=kie_key)

    scene_models()
    print_header("LES JOUEURS")

    for m in masq.get_available_models():
        status = f"{C.GOLD}â—†{C.RESET}" if m["available"] else f"{C.DIM}â—‹{C.RESET}"
        cost = f"${m['cost']:.4f}" if m["cost"] > 0 else f"{C.GREEN}GRATIS{C.RESET}"
        print(f"  {status} {C.BOLD}{m['id']}{C.RESET}")
        print(f"      {m['name']} ({m['provider']}) Â· {cost}")
        if m.get("notes"):
            print(f"      {C.DIM}{m['notes']}{C.RESET}")

    print()
    if not runware_key:
        print_status(f"{C.GOLD}Tip:{C.RESET} Set RUNWARE_API_KEY to unlock more cards, cher")
    if not kie_key:
        print_status(f"{C.GOLD}Tip:{C.RESET} Set KIE_API_KEY for de Kie.ai ace")

    return 0


# ==================== Main ====================

def main():
    parser = argparse.ArgumentParser(
        description="Masq - Background removal & upscaling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  masq bg photo.png                    # Masquerade (all masks)
  masq bg photo.png -m runware_rmbg2   # Single mask
  masq upscale logo.png --scale 4      # Upscale 4x (fast, Lanczos)
  masq upscale logo.png --hd           # Upscale HD (Real-ESRGAN, slower)
  masq upscale logo.png --hd --anime   # HD with anime model (for artwork)
  masq models                          # List available masks

Environment:
  RUNWARE_API_KEY    Runware API key for cloud masks
  KIE_API_KEY        Kie.ai API key for Recraft mask
        """
    )
    parser.add_argument("--no-banner", action="store_true", help="Skip banner")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # bg command
    bg_parser = subparsers.add_parser("bg", help="Remove background from image")
    bg_parser.add_argument("input", help="Input image file")
    bg_parser.add_argument("-o", "--output", help="Output file (single model mode)")
    bg_parser.add_argument("-d", "--output-dir", help="Output directory (shotgun mode)")
    bg_parser.add_argument("-m", "--model", help="Use specific mask (skips masquerade)")
    bg_parser.add_argument("--models", help="Comma-separated list of masks")

    # upscale command
    up_parser = subparsers.add_parser("upscale", help="Upscale image")
    up_parser.add_argument("input", help="Input image file")
    up_parser.add_argument("-o", "--output", help="Output file")
    up_parser.add_argument("-s", "--scale", type=int, default=4, help="Scale factor (default: 4)")
    up_parser.add_argument("--no-alpha", action="store_true", help="Don't preserve transparency")
    # HD mode options
    up_parser.add_argument("--hd", action="store_true", help="HD mode (Real-ESRGAN, slower but better quality)")
    up_parser.add_argument("--anime", action="store_true", help="Use anime model (for illustrations/logos)")
    up_parser.add_argument("--tile", type=int, default=256, help="Tile size for HD mode (lower = less VRAM)")

    # models command
    subparsers.add_parser("models", help="List available masks")

    args = parser.parse_args()

    if not args.no_banner:
        print_banner()

    # Run command
    if args.command == "bg":
        exit_code = asyncio.run(cmd_bg(args))
    elif args.command == "upscale":
        exit_code = asyncio.run(cmd_upscale(args))
    elif args.command == "models":
        exit_code = asyncio.run(cmd_models(args))
    else:
        parser.print_help()
        exit_code = 1

    print()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
