# src/scripts/generate_tts.py

import logging
from pathlib import Path
from typing import List, Optional
import json

from src.utils.config import ConfigManager
from src.generators.tts_generator import TTSGenerator


def generate_tts_content(batch_ids: Optional[List[str]] = None) -> int:
    """Generate TTS audio content from processed segments.

    Args:
        batch_ids: Optional list of specific batch IDs to process

    Returns:
        int: Number of segments processed
    """
    # Load configuration
    config = ConfigManager()

    # Initialize TTS generator
    generator = TTSGenerator(config)

    # If no batch_ids provided, load from manifest
    if batch_ids is None:
        manifest_path = Path(config.content_paths['metadata']) / "latest_batch_manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
                batch_ids = manifest['batches']
        else:
            logging.error("No batch manifest found and no batch_ids provided")
            return 0

    try:
        # Process all pending batches
        results = generator.process_all_pending()

        # Return total number of processed segments
        total_segments = sum(len(result['segments']) for result in results)
        logging.info(f"Generated TTS audio for {total_segments} segments across {len(results)} batches")

        return total_segments

    except Exception as e:
        logging.error(f"Error in TTS generation: {str(e)}")
        raise


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Example usage
    batch_ids = ["batch_general_todayilearned_20241205_215115"]
    total_segments = generate_tts_content(batch_ids)
    print(f"Generated audio for {total_segments} segments")

