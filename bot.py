#!/usr/bin/env python3
"""
Masq Standalone Discord Bot
Background removal (shotgun) + Lanczos upscaling.

Usage:
    python bot.py

Environment:
    DISCORD_TOKEN       Discord bot token (required)
    RUNWARE_API_KEY     Runware API key (optional, enables cloud models)
    KIE_API_KEY         Kie.ai API key (optional, enables Recraft model)
"""

import asyncio
import io
import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("masq")

# Suppress noisy loggers
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)


BANNER = r"""
                              ╭─────────────────────╮
    ███╗   ███╗ █████╗ ███████╗ ██████╗             │
    ████╗ ████║██╔══██╗██╔════╝██╔═══██╗            │
    ██╔████╔██║███████║███████╗██║   ██║  ◈ ◈ ◈    │
    ██║╚██╔╝██║██╔══██║╚════██║██║▄▄ ██║            │
    ██║ ╚═╝ ██║██║  ██║███████║╚██████╔╝            │
    ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝ ╚══▀▀═╝             │
                              ╰─────────────────────╯
                        [ DISCORD BOT ]
"""


class MasqBot(commands.Bot):
    """Standalone Masq Discord Bot."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            description="Masq - Background removal & upscaling"
        )

    async def setup_hook(self):
        """Load cogs and sync commands."""
        logger.info("Loading Masq cog...")
        await self.load_extension("cogs.masq.cog")
        logger.info("Syncing slash commands...")
        await self.tree.sync()
        logger.info("Commands synced!")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Guilds: {len(self.guilds)}")

        # Set status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="/bg | /upscale"
        )
        await self.change_presence(activity=activity)

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        logger.error(f"Command error: {error}")


async def main():
    print(BANNER)

    # Validate environment
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("DISCORD_TOKEN not set!")
        logger.info("Set DISCORD_TOKEN in .env or environment")
        sys.exit(1)

    # Log API key status
    runware = os.getenv("RUNWARE_API_KEY")
    kie = os.getenv("KIE_API_KEY")

    logger.info("API Keys:")
    logger.info(f"  RUNWARE_API_KEY: {'◈ Set' if runware else '○ Not set (Runware models unavailable)'}")
    logger.info(f"  KIE_API_KEY:     {'◈ Set' if kie else '○ Not set (Kie models unavailable)'}")
    logger.info("")

    # Start bot
    bot = MasqBot()

    try:
        await bot.start(token)
    except discord.LoginFailure:
        logger.error("Invalid Discord token!")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bot.close()


if __name__ == "__main__":
    asyncio.run(main())
