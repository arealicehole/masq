"""
Masq Discord Cog
Background removal (shotgun) + Lanczos upscaling

Usage:
    # As a cog in your existing bot
    from cogs.masq import MasqCog
    await bot.add_cog(MasqCog(bot))

    # Or use the core engine directly
    from cogs.masq import Masq
    masq = Masq(runware_key="...", kie_key="...")
    result = await masq.remove_background(image_bytes)
"""

from .core import Masq, ShotgunResult, UpscaleResult, MODELS, DEFAULT_SHOTGUN_MODELS
from .cog import MasqCog

__all__ = ["Masq", "MasqCog", "ShotgunResult", "UpscaleResult", "MODELS", "DEFAULT_SHOTGUN_MODELS"]
