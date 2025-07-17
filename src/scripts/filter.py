# src/scripts/filter.py

import logging
import json
from pathlib import Path
from typing import List, Optional
from src.utils.config import ConfigManager
from src.processors.content_filter import ContentFilter


def filter_content(batch_ids: Optional[List[str]] = None):
    """
    Filter Reddit content to find segments suitable for video production.

    Args:
        batch_ids: Optional list of specific batch IDs to process.
                  If None, will process all batches from the latest manifest.
    """
    # Load configuration
    config = ConfigManager()

    # Initialize filter
    content_filter = ContentFilter(config)

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

    raw_dir = Path(config.content_paths['raw'])
    total_segments = 0

    # Process each batch
    for batch_id in batch_ids:
        try:
            # Construct batch file path
            batch_path = raw_dir / f"{batch_id}.json"

            if not batch_path.exists():
                logging.warning(f"Batch file not found: {batch_path}")
                continue

            # Filter the batch
            segments = content_filter.process_batch(str(batch_path))

            # Save filtered segments
            content_filter.save_filtered_segments(segments, batch_id)

            total_segments += len(segments)
            logging.info(f"Filtered batch {batch_id}: {len(segments)} segments")

        except Exception as e:
            logging.error(f"Error filtering batch {batch_id}: {str(e)}")
            continue

    logging.info(f"Completed filtering {len(batch_ids)} batches, found {total_segments} good segments")
    return total_segments


if __name__ == "__main__":
    # Example usage
    filter_content()
