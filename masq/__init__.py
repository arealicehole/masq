"""
Masq - Image Processing Engine
Background removal (shotgun) + Lanczos upscaling

Built by Tricon Digital (https://tricondigital.com)
"""

__version__ = "1.0.0"
__author__ = "Tricon Digital"

from cogs.masq.core import Masq, ShotgunResult, UpscaleResult

__all__ = ["Masq", "ShotgunResult", "UpscaleResult"]
