# src/main.py

import logging
from typing import List, Optional, Dict, Any
import asyncio
from pathlib import Path

from src.scripts.scrape import scrape_content
from src.scripts.filter import filter_content
from src.scripts.prepare_tts import prepare_tts_content
from src.scripts.generate_tts import generate_tts_content
from src.scripts.generate_videos import generate_videos
from src.scripts.generate_thumbnails import generate_thumbnails
from src.utils.config import ConfigManager


"""
Automated Content Generation Pipeline
Main orchestration script for end-to-end content processing
"""


def group_batches_by_topic(batch_ids: List[str]) -> Dict[str, List[str]]:
    """Group batch IDs by their topic."""
    topic_batches = {}
    for batch_id in batch_ids:
        parts = batch_id.split('_')
        if len(parts) >= 2 and parts[0] == 'batch':
            topic = parts[1]
            topic_batches.setdefault(topic, []).append(batch_id)
    return topic_batches


async def run_async_tasks(topic_batches: Dict[str, List[str]], config: ConfigManager):
    """Run all async tasks together."""
    # Video generation tasks
    video_tasks = [
        generate_videos(topic, topic_batch_ids)
        for topic, topic_batch_ids in topic_batches.items()
    ]
    await asyncio.gather(*video_tasks)
    logging.info("Video generation complete")

    # Thumbnail generation
    num_thumbnails = await generate_thumbnails(config)
    logging.info(f"Generated {num_thumbnails} thumbnails")


def run_pipeline(batch_ids: Optional[List[str]] = None) -> None:
    """Run the complete content generation pipeline."""
    logging.info("Starting content pipeline")
    config = ConfigManager()

    try:
        # Stage 1: Scraping (if no batch_ids provided)
        if not batch_ids:
            batch_ids = scrape_content()
            if not batch_ids:
                logging.warning("No batches were created during scraping")
                return
            logging.info(f"Scraping complete. Created {len(batch_ids)} batches")

        # Stage 2: Filtering
        num_filtered = filter_content(batch_ids)
        if num_filtered == 0:
            logging.warning("No segments passed filtering")
            return
        logging.info(f"Filtering complete. {num_filtered} segments filtered")

        # Stage 3: TTS Preparation
        num_prepared = prepare_tts_content(batch_ids)
        if num_prepared == 0:
            logging.warning("No segments prepared for TTS")
            return
        logging.info(f"TTS preparation complete. {num_prepared} segments prepared")

        # Stage 4: TTS Generation
        num_generated = generate_tts_content(batch_ids)
        if num_generated == 0:
            logging.warning("No audio segments generated")
            return
        logging.info(f"TTS generation complete. {num_generated} segments generated")

        # Stage 5 & 6: Video and Thumbnail Generation (async)
        topic_batches = group_batches_by_topic(batch_ids)
        asyncio.run(run_async_tasks(topic_batches, config))

    except Exception as e:
        logging.error(f"Pipeline error: {str(e)}", exc_info=True)
        raise


def test():
    """Test specific components of the pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info("Starting test mode")
    config = ConfigManager()

    # Example: Test video and thumbnail generation with existing batch IDs
    batch_ids =["batch_general_AskReddit_20250329_144516", "batch_general_todayilearned_20250329_144516", "batch_general_explainlikeimfive_20250329_144516", "batch_general_tifu_20250329_144516", "batch_general_MaliciousCompliance_20250329_144516", "batch_general_LifeProTips_20250329_144516", "batch_general_NoStupidQuestions_20250329_144516", "batch_general_confessions_20250329_144516", "batch_tech_technology_20250329_144516", "batch_tech_programming_20250329_144516", "batch_tech_TalesFromTechSupport_20250329_144516", "batch_tech_ProgrammerHumor_20250329_144516", "batch_tech_techsupportgore_20250329_144517", "batch_tech_gadgets_20250329_144516", "batch_tech_buildapc_20250329_144516", "batch_tech_pcmasterrace_20250329_144516", "batch_tech_cybersecurity_20250329_144516", "batch_tech_dataisbeautiful_20250329_144517", "batch_tech_sysadmin_20250329_144516", "batch_tech_EngineeringPorn_20250329_144517", "batch_tech_mac_20250329_144517", "batch_tech_windows_20250329_144517", "batch_tech_apple_20250329_144517", "batch_tech_hardware_20250329_144517", "batch_tech_networking_20250329_144517", "batch_tech_cscareerquestions_20250329_144517", "batch_tech_webdev_20250329_144517", "batch_tech_MachineLearning_20250329_144517", "batch_tech_privacy_20250329_144517", "batch_tech_netsec_20250329_144517", "batch_pop_movies_20250329_144517", "batch_pop_television_20250329_144517", "batch_pop_gaming_20250329_144517", "batch_pop_FanTheories_20250329_144517", "batch_pop_gamedev_20250329_144517", "batch_pop_MovieDetails_20250329_144517", "batch_pop_patientgamers_20250329_144517", "batch_pop_anime_20250329_144517", "batch_pop_MarvelStudios_20250329_144517", "batch_pop_NetflixBestOf_20250329_144517", "batch_pop_comicbooks_20250329_144517", "batch_pop_TrueGaming_20250329_144517", "batch_pop_HobbyDrama_20250329_144517", "batch_pop_PrequelMemes_20250329_144720", "batch_pop_freefolk_20250329_144517", "batch_pop_thewalkingdead_20250329_144517", "batch_pop_startrek_20250329_144517", "batch_pop_harrypotter_20250329_144517", "batch_pop_StrangerThings_20250329_144517", "batch_pop_BetterCallSaul_20250329_144840", "batch_pop_theoffice_20250329_145000", "batch_pop_DunderMifflin_20250329_145005", "batch_pop_SquaredCircle_20250329_145017", "batch_pop_DCcomics_20250329_145015", "batch_pop_StarWars_20250329_145004"]

    num_generated = generate_tts_content(batch_ids)
    if num_generated == 0:
        logging.warning("No audio segments generated")
        return
    logging.info(f"TTS generation complete. {num_generated} segments generated")
    topic_batches = group_batches_by_topic(batch_ids)
    asyncio.run(run_async_tasks(topic_batches, config))


def main():
    """Main entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    run_pipeline()  # Now runs sync and async parts properly


if __name__ == "__main__":
    # For testing specific components:
    test()

    # For running the full pipeline:
    # main()

