# src/scripts/generate_videos.py

import asyncio
import logging
from pathlib import Path
from typing import List, Dict
import json
from datetime import datetime, timedelta
import subprocess

from src.generators.video.ffmpeg_generator import FFmpegVideoGenerator
from src.utils.config import ConfigManager


async def generate_videos(topic: str, batch_ids: List[str], num_days: int = 8):
    """
    Generate videos for a topic, organizing output by date for easy upload processing.

    Args:
        topic: Topic/channel category (general, tech, pop)
        batch_ids: List of batch IDs to process
        num_days: Number of days worth of content to generate (default: 1)
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    config = ConfigManager()
    video_generator = FFmpegVideoGenerator(config._config)

    # Collect and sort segments
    all_segments = []
    for batch_id in batch_ids:
        content_path = Path(config.content_paths['processed']) / f"tts_ready_{batch_id}.json"
        if not content_path.exists():
            logger.warning(f"No processed content found for batch {batch_id}")
            continue

        with open(content_path, 'r') as f:
            batch_content = json.load(f)
            for segment in batch_content:
                segment['batch_id'] = batch_id
                all_segments.append(segment)

    if not all_segments:
        logger.warning(f"No content found for topic: {topic}")
        return

    # Sort segments by engagement score
    all_segments.sort(
        key=lambda x: x['metadata']['engagement_score']
        if isinstance(x.get('metadata', {}), dict) else 0,
        reverse=True
    )

    shorts_per_day = 3  # Number of shorts to generate per day
    segments_per_longform = 14  # Number of segments per longform video

    # Generate videos for specified number of days
    tasks = []
    for day in range(num_days):
        date = (datetime.now() + timedelta(days=day)).strftime('%Y%m%d')

        # Calculate segment indices for this day
        shorts_per_day = 3
        day_start_idx = day * segments_per_longform
        shorts_end_idx = day_start_idx + shorts_per_day
        longform_end_idx = day_start_idx + segments_per_longform

        # Prepare shorts generation task
        """day_segments = all_segments[day_start_idx:shorts_end_idx]
        if day_segments:
            shorts_task = generate_topic_shorts(
                video_generator=video_generator,
                segments=day_segments,
                topic=topic,
                config=config,
                date=date
            )
            tasks.append(shorts_task)"""

        # Prepare longform compilation task
        longform_segments = all_segments[day_start_idx:longform_end_idx]  # Take X segments for longform
        if longform_segments:
            longform_task = generate_topic_compilation(
                video_generator=video_generator,
                segments=longform_segments,
                topic=topic,
                config=config,
                date=date
            )
            tasks.append(longform_task)

    # Run all video generation tasks in parallel
    await asyncio.gather(*tasks)


async def generate_topic_shorts(video_generator: FFmpegVideoGenerator,
                                segments: List[Dict],
                                topic: str,
                                config: ConfigManager,
                                date: str) -> None:
    """Generate short-form videos with consistent naming convention."""
    logger = logging.getLogger(__name__)

    # Create topic/date-specific directory
    shorts_dir = Path(config.content_paths['videos']) / 'shorts' / topic / date
    shorts_dir.mkdir(parents=True, exist_ok=True)

    for i, segment in enumerate(segments):
        try:
            audio_path = Path(config.content_paths['audio']) / segment['batch_id'] / f"{segment['segment_id']}"

            # Consistent naming: {topic}_short_{date}_{index}.mp4
            output_path = shorts_dir / f"{topic}_short_{date}_{i:02d}.mp4"

            text_content = {
                'title': segment['metadata']['title'],
                'text': '\n'.join(block['text'] for block in segment['speaker_blocks']),
                'duration': segment['metadata']['duration_estimate']
            }

            await video_generator.generate_short(
                audio_path=audio_path,
                text_content=text_content,
                output_path=output_path
            )

            logger.info(f"Generated short video: {output_path}")

        except Exception as e:
            logger.error(f"Error generating short video for segment {i}: {str(e)}")
            continue


async def generate_topic_compilation(video_generator: FFmpegVideoGenerator,
                                     segments: List[Dict],
                                     topic: str,
                                     config: ConfigManager,
                                     date: str) -> None:
    """Generate long-form compilation with consistent naming convention."""
    logger = logging.getLogger(__name__)

    try:
        # Create topic-specific directory
        longform_dir = Path(config.content_paths['videos']) / 'longform' / topic / date
        longform_dir.mkdir(parents=True, exist_ok=True)

        # Process segments and generate video
        selected_segments = []
        current_duration = 0

        for segment in segments:
            audio_base_path = Path(config.content_paths['audio']) / segment['batch_id'] / segment['segment_id']

            # Process audio files
            audio_files = sorted(list(audio_base_path.glob('block_*.wav')))
            if not audio_files:
                continue

            # Create combined audio
            concat_audio_path = audio_base_path / "combined_audio.wav"
            audio_list_file = audio_base_path / "audio_list.txt"

            with open(audio_list_file, 'w') as f:
                for audio_file in audio_files:
                    f.write(f"file '{audio_file.absolute()}'\n")

            try:
                subprocess.run([
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(audio_list_file),
                    '-c', 'copy',
                    '-y',
                    str(concat_audio_path)
                ], check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to concatenate audio files: {e}")
                continue

            # Add segment to selection
            segment_duration = segment['metadata']['duration_estimate']
            selected_segments.append({
                'audio_path': concat_audio_path,
                'text_content': {
                    'text': '\n'.join(block['text'] for block in segment['speaker_blocks']),
                    'duration': segment_duration
                }
            })
            current_duration += segment_duration

            # Clean up audio list file
            audio_list_file.unlink()

        if selected_segments:
            # Consistent naming: {topic}_longform_{date}.mp4
            output_path = longform_dir / f"{topic}_longform_{date}.mp4"

            await video_generator.generate_longform(
                segments=selected_segments,
                output_path=output_path
            )

            logger.info(f"Generated long-form compilation: {output_path}")

            # Clean up temporary audio files
            for segment in selected_segments:
                try:
                    Path(segment['audio_path']).unlink()
                except Exception as e:
                    logger.warning(f"Failed to clean up temp audio file: {e}")

    except Exception as e:
        logger.error(f"Error generating topic compilation: {str(e)}")
        raise

