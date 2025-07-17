# src/scripts/prepare_tts.py

import logging
from pathlib import Path
from typing import List, Optional
import json

from src.utils.config import ConfigManager
from src.processors.tts_processor import TTSProcessor


def prepare_tts_content(batch_ids: Optional[List[str]] = None):
    """Prepare filtered content for TTS processing."""
    # Load configuration
    config = ConfigManager()

    # Initialize TTS processor
    processor = TTSProcessor(config)

    # If no batch_ids provided, load from manifest
    if batch_ids is None:
        manifest_path = Path(config.content_paths['metadata']) / "latest_batch_manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
                batch_ids = manifest['batches']
        else:
            logging.error("No batch manifest found and no batch_ids provided")
            return

    filtered_dir = Path(config.content_paths['filtered'])
    total_segments = 0

    # Process each filtered batch
    for batch_id in batch_ids:
        try:
            # Look for filtered batch file
            filtered_path = filtered_dir / f"filtered_{batch_id}.json"

            if not filtered_path.exists():
                logging.warning(f"Filtered batch file not found: {filtered_path}")
                continue

            # Process for TTS
            tts_segments = processor.process_filtered_batch(str(filtered_path))

            # Save TTS-ready segments
            processor.save_tts_segments(tts_segments, batch_id)

            total_segments += len(tts_segments)
            logging.info(f"Prepared {len(tts_segments)} segments for TTS from batch {batch_id}")

        except Exception as e:
            logging.error(f"Error preparing batch {batch_id} for TTS: {str(e)}")
            continue

    logging.info(f"Completed TTS preparation for {len(batch_ids)} batches, total {total_segments} segments")
    return total_segments


if __name__ == "__main__":
    # Example usage
    batch_ids = ["batch_general_todayilearned_20241205_215115"]
    prepare_tts_content(batch_ids)