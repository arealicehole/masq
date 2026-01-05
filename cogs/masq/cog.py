"""
Masq Discord Cog
Background removal (shotgun) + Lanczos upscaling for Tricon Lab.

Commands:
    /bg <image> [model]      - Remove background (shotgun or single model)
    /upscale <image> [scale] - Upscale image (Lanczos, preserves alpha)
"""

import asyncio
import io
import logging
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .core import Masq, MODELS, DEFAULT_SHOTGUN_MODELS

logger = logging.getLogger(__name__)

# Credit costs for Governor integration
CREDIT_COSTS = {
    "bg_shotgun": 5,      # 5 credits for full shotgun (runs 5 models)
    "bg_single": 1,       # 1 credit for single model
    "upscale": 1,         # 1 credit for upscale
}


class ModelSelectView(discord.ui.View):
    """View with buttons for selecting the best model result."""

    def __init__(self, results: list, user_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.results = results
        self.user_id = user_id
        self.selected_model: Optional[str] = None

        # Add a button for each successful result
        for i, result in enumerate(results):
            if result.is_success:
                button = discord.ui.Button(
                    label=f"{i+1}. {result.model_name}",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"select_{result.model_id}"
                )
                button.callback = self._make_callback(result.model_id)
                self.add_item(button)

    def _make_callback(self, model_id: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message(
                    "This isn't your result set.",
                    ephemeral=True
                )
                return

            self.selected_model = model_id
            model_name = MODELS.get(model_id, {}).get("name", model_id)

            # Disable all buttons
            for item in self.children:
                item.disabled = True

            await interaction.response.edit_message(
                content=f"Selected: **{model_name}**",
                view=self
            )
            self.stop()

        return callback

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class MasqCog(commands.Cog):
    """
    Masq Image Processing Cog for Tricon Lab.

    Provides background removal (shotgun approach) and Lanczos upscaling.
    Integrates with Governor rate limiting system.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.masq = Masq(
            runware_key=os.getenv("RUNWARE_API_KEY"),
            kie_key=os.getenv("KIE_API_KEY")
        )

    async def cog_unload(self):
        await self.masq.close()

    # ==================== /bg Command ====================

    @app_commands.command(name="bg", description="Remove background from an image")
    @app_commands.describe(
        image="Image to process (PNG, JPG, WebP)",
        model="Specific model to use (optional - runs all 5 if not specified)"
    )
    @app_commands.choices(model=[
        app_commands.Choice(name="RMBG 2.0 (Best Overall)", value="runware_rmbg2"),
        app_commands.Choice(name="BiRefNet Portrait", value="runware_birefnet_portrait"),
        app_commands.Choice(name="Recraft BG (Kie)", value="kie_recraft"),
        app_commands.Choice(name="BiRefNet General (Local)", value="local_birefnet"),
        app_commands.Choice(name="ISNet (Local)", value="local_isnet"),
    ])
    async def bg_command(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        model: Optional[str] = None
    ):
        """Remove background from an image using AI models."""

        # Validate attachment
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message(
                "Please upload an image file (PNG, JPG, WebP).",
                ephemeral=True
            )
            return

        # Check file size (10MB limit for Discord)
        if image.size > 10 * 1024 * 1024:
            await interaction.response.send_message(
                "Image too large. Maximum size: 10MB",
                ephemeral=True
            )
            return

        # Defer (this may take a while)
        await interaction.response.defer()

        try:
            # Download image
            image_bytes = await image.read()

            if model:
                # Single model mode
                result = await self.masq.remove_background_single(image_bytes, model)

                if not result.is_success:
                    await interaction.followup.send(
                        f"Background removal failed: {result.error}",
                        ephemeral=True
                    )
                    return

                # Send result
                file = discord.File(
                    io.BytesIO(result.image_bytes),
                    filename=f"bg_removed_{result.model_id}.png"
                )
                embed = discord.Embed(
                    title="Background Removed",
                    color=0x7B68EE  # Medium purple - masquerade vibe
                )
                embed.add_field(name="Model", value=result.model_name, inline=True)
                embed.add_field(name="Time", value=f"{result.processing_time_ms:.0f}ms", inline=True)
                embed.add_field(name="Cost", value=f"${result.cost:.4f}", inline=True)
                embed.set_footer(text="Masq by Tricon Digital")

                await interaction.followup.send(embed=embed, file=file)

                # Log for analytics
                await self._log_usage(interaction.user, "bg_single", model, result.cost)

            else:
                # Shotgun mode (all models)
                result = await self.masq.remove_background(image_bytes)

                if not result.successful:
                    errors = [r.error for r in result.results if r.error]
                    await interaction.followup.send(
                        f"All models failed. Errors:\n" + "\n".join(errors[:3]),
                        ephemeral=True
                    )
                    return

                # Send all successful results
                files = []
                embed = discord.Embed(
                    title="Background Removal - Pick Your Favorite",
                    description="Select the best result below to help improve recommendations.",
                    color=0x9370DB  # Medium purple
                )

                for i, r in enumerate(result.successful):
                    files.append(discord.File(
                        io.BytesIO(r.image_bytes),
                        filename=f"{i+1}_{r.model_id}.png"
                    ))
                    embed.add_field(
                        name=f"{i+1}. {r.model_name}",
                        value=f"{r.provider} | {r.processing_time_ms:.0f}ms | ${r.cost:.4f}",
                        inline=True
                    )

                embed.set_footer(
                    text=f"Total: {result.total_time_ms:.0f}ms | ${result.total_cost:.4f} | Masq by Tricon Digital"
                )

                # Create selection view
                view = ModelSelectView(result.successful, interaction.user.id)

                await interaction.followup.send(embed=embed, files=files, view=view)

                # Wait for selection and log it
                await view.wait()
                if view.selected_model:
                    await self._log_selection(interaction.user, view.selected_model)

                # Log usage
                await self._log_usage(interaction.user, "bg_shotgun", "all", result.total_cost)

        except Exception as e:
            logger.exception(f"BG removal error: {e}")
            await interaction.followup.send(
                f"Error processing image: {str(e)[:200]}",
                ephemeral=True
            )

    # ==================== /upscale Command ====================

    @app_commands.command(name="upscale", description="Upscale an image (preserves transparency)")
    @app_commands.describe(
        image="Image to upscale (PNG, JPG, WebP)",
        scale="Scale factor (2x or 4x). Default: 4x",
        mode="fast (instant) or premium (AI, 1-2 min but better quality)"
    )
    @app_commands.choices(
        scale=[
            app_commands.Choice(name="2x", value=2),
            app_commands.Choice(name="4x (Default)", value=4),
        ],
        mode=[
            app_commands.Choice(name="fast (instant)", value="fast"),
            app_commands.Choice(name="premium (AI, ~1-2 min)", value="premium"),
        ]
    )
    async def upscale_command(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        scale: int = 4,
        mode: str = "fast"
    ):
        """Upscale an image. Fast uses Lanczos, Premium uses Real-ESRGAN AI."""

        # Validate attachment
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.response.send_message(
                "Please upload an image file (PNG, JPG, WebP).",
                ephemeral=True
            )
            return

        # Check file size
        if image.size > 10 * 1024 * 1024:
            await interaction.response.send_message(
                "Image too large. Maximum size: 10MB",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        try:
            image_bytes = await image.read()

            if mode == "premium":
                # Premium mode - Real-ESRGAN (slower but reconstructs detail)
                from .realesrgan import upscale_hd
                from PIL import Image

                # Check input dimensions - warn for large images (CPU is slow)
                img_check = Image.open(io.BytesIO(image_bytes))
                max_dim = max(img_check.size)
                pixels = img_check.size[0] * img_check.size[1]

                # Estimate time: ~10s per 256x256 tile on CPU
                est_tiles = (img_check.size[0] // 256 + 1) * (img_check.size[1] // 256 + 1)
                est_minutes = (est_tiles * 10) / 60

                # Send a heads-up message with time estimate
                time_msg = f"~{est_minutes:.0f} min" if est_minutes >= 1 else "~1 min"
                await interaction.followup.send(
                    f"🎨 **Premium upscale started** ({img_check.size[0]}x{img_check.size[1]} → "
                    f"{img_check.size[0]*scale}x{img_check.size[1]*scale})\n"
                    f"Estimated time: **{time_msg}** on CPU. Please wait...",
                    ephemeral=False
                )

                result = await upscale_hd(image_bytes, scale=scale, model="default")

                if not result.success:
                    await interaction.followup.send(
                        f"Upscaling failed: {result.error}",
                        ephemeral=True
                    )
                    return

                # Check output size
                if len(result.image_bytes) > 25 * 1024 * 1024:
                    await interaction.followup.send(
                        f"Result too large to upload ({len(result.image_bytes) / 1024 / 1024:.1f}MB). "
                        f"Try a smaller scale factor.",
                        ephemeral=True
                    )
                    return

                file = discord.File(
                    io.BytesIO(result.image_bytes),
                    filename=f"upscaled_premium_{scale}x.webp"
                )

                embed = discord.Embed(
                    title=f"Premium Upscaled {scale}x",
                    description="AI-enhanced with Real-ESRGAN",
                    color=0xFFD700  # Gold for premium
                )
                embed.add_field(
                    name="Original",
                    value=f"{result.original_size[0]}x{result.original_size[1]}",
                    inline=True
                )
                embed.add_field(
                    name="Upscaled",
                    value=f"{result.upscaled_size[0]}x{result.upscaled_size[1]}",
                    inline=True
                )
                embed.add_field(
                    name="Time",
                    value=f"{result.processing_time_ms/1000:.1f}s",
                    inline=True
                )
                if result.has_alpha:
                    embed.add_field(
                        name="Transparency",
                        value="Preserved",
                        inline=True
                    )
                embed.set_footer(text="Masq by Tricon Digital | Real-ESRGAN AI")

                await interaction.followup.send(embed=embed, file=file)

                # Log usage
                await self._log_usage(interaction.user, "upscale_premium", f"{scale}x", 0.0)

            else:
                # Fast mode - Lanczos (instant)
                result = await self.masq.upscale(image_bytes, scale=scale)

                if not result.success:
                    await interaction.followup.send(
                        f"Upscaling failed: {result.error}",
                        ephemeral=True
                    )
                    return

                # Check output size (Discord limit 25MB)
                if len(result.image_bytes) > 25 * 1024 * 1024:
                    await interaction.followup.send(
                        f"Result too large to upload ({len(result.image_bytes) / 1024 / 1024:.1f}MB). "
                        f"Try a smaller scale factor.",
                        ephemeral=True
                    )
                    return

                file = discord.File(
                    io.BytesIO(result.image_bytes),
                    filename=f"upscaled_{scale}x.webp"
                )

                embed = discord.Embed(
                    title=f"Upscaled {scale}x",
                    color=0x7B68EE
                )
                embed.add_field(
                    name="Original",
                    value=f"{result.original_size[0]}x{result.original_size[1]}",
                    inline=True
                )
                embed.add_field(
                    name="Upscaled",
                    value=f"{result.upscaled_size[0]}x{result.upscaled_size[1]}",
                    inline=True
                )
                embed.add_field(
                    name="Time",
                    value=f"{result.processing_time_ms:.0f}ms",
                    inline=True
                )
                if result.has_alpha:
                    embed.add_field(
                        name="Transparency",
                        value="Preserved",
                        inline=True
                    )
                embed.set_footer(text="Masq by Tricon Digital | Lanczos Resampling")

                await interaction.followup.send(embed=embed, file=file)

                # Log usage
                await self._log_usage(interaction.user, "upscale", f"{scale}x", 0.0)

        except Exception as e:
            logger.exception(f"Upscale error: {e}")
            await interaction.followup.send(
                f"Error upscaling image: {str(e)[:200]}",
                ephemeral=True
            )

    # ==================== Analytics/Logging ====================

    async def _log_usage(
        self,
        user: discord.User,
        tool: str,
        params: str,
        cost: float
    ):
        """Log tool usage for analytics and Governor integration."""
        logger.info(
            f"USAGE | user={user.id} | tool={tool} | params={params} | cost=${cost:.4f}"
        )

        # If Governor/database cog exists, log there too
        # This integrates with Tricon Lab's credit system
        if hasattr(self.bot, "governor"):
            try:
                await self.bot.governor.log_usage(
                    user_id=user.id,
                    tool_name=f"masq_{tool}",
                    cost=cost
                )
            except Exception as e:
                logger.warning(f"Failed to log to Governor: {e}")

    async def _log_selection(self, user: discord.User, model_id: str):
        """Log which model the user selected as best."""
        logger.info(f"SELECTION | user={user.id} | selected={model_id}")

        # This data helps improve model recommendations
        # Could store in DB for analytics dashboard


async def setup(bot: commands.Bot):
    """Setup function for loading the cog."""
    await bot.add_cog(MasqCog(bot))
