# src/scripts/generate_thumbnails.py

import asyncio
import logging
from typing import Optional

from src.generators.thumbnail_generator import ThumbnailGenerator
from src.utils.config import ConfigManager


async def generate_thumbnails(config: Optional[ConfigManager] = None) -> int:
    """
    Generate thumbnails for all pending videos.

    Args:
        config: Optional ConfigManager instance

    Returns:
        Number of thumbnails generated
    """
    if config is None:
        config = ConfigManager()

    generator = ThumbnailGenerator(config._config)
    return await generator.generate_all_pending()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    asyncio.run(generate_thumbnails())