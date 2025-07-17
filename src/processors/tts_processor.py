# src/processors/tts_processor.py

from pathlib import Path
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import re

from src.utils.config import ConfigManager


@dataclass
class TTSSegment:
    """Represents a segment ready for TTS processing"""
    segment_id: str  # Unique identifier for the segment
    speaker_blocks: List[Dict[str, str]]  # List of text blocks with speaker assignments
    metadata: Dict[str, Any]  # Additional information for video production


class TTSProcessor:
    """Processes filtered content into TTS-ready format with speaker assignments."""

    def __init__(self, config: ConfigManager):
        """Initialize the TTS processor with configuration.

        The processor handles converting filtered Reddit content into a format
        optimized for Text-to-Speech production, including speaker assignments
        and proper formatting of text for natural speech.
        """
        self.config = config
        self.tts_settings = config.tts_settings
        self.paths = config.content_paths

        logging.basicConfig(level=logging.INFO)

    def clean_for_tts(self, text: str) -> str:
        """Clean and format text specifically for TTS processing.

        Handles common issues that can affect TTS quality:
        - Removes URLs and markdown
        - Standardizes punctuation
        - Adds pauses for better pacing
        - Formats numbers and symbols for better pronunciation
        """
        # Remove URLs and Markdown formatting
        text = re.sub(r'http\S+|www\.\S+', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

        # Standardize punctuation for better speech flow
        text = text.replace('...', self.tts_settings['formatting']['pause_long'])
        text = text.replace('--', self.tts_settings['formatting']['pause_short'])

        # Format numbers for better pronunciation
        text = re.sub(r'(\d+)k\b', r'\1 thousand', text)
        text = re.sub(r'(\d+(\.\d+)?)[mM]\b', r'\1 million', text)

        # Add pauses after sentence endings
        text = re.sub(r'([.!?])\s+', r'\1' + self.tts_settings['formatting']['pause_short'] + ' ', text)

        # Clean up extra whitespace
        text = ' '.join(text.split())

        return text

    def create_speaker_blocks(self, segment: Dict) -> List[Dict[str, str]]:
        """Convert a segment into a series of speaker blocks for TTS.

        This improved version handles multiple comment chains under the same title,
        creating a more natural conversation flow without title repetition.

        Args:
            segment: Dictionary containing the segment data with grouped comments

        Returns:
            List[Dict[str, str]]: Sequence of speaker blocks for TTS processing
        """
        blocks = []

        # Narrate the title once at the start
        blocks.append({
            'speaker': 'narrator',
            'text': self.clean_for_tts(f"{segment['title']}")
        })

        # Process each comment chain in the conversation
        for i, comment in enumerate(segment['comments']):
            # Add main comment
            blocks.append({
                'speaker': 'commenter',
                'text': self.clean_for_tts(comment['text'])
            })

            # Process replies for this comment
            for j, reply in enumerate(comment.get('replies', [])):

                blocks.append({
                    'speaker': 'replier',
                    'text': self.clean_for_tts(reply['text'])
                })

        return blocks

    def process_segment(self, segment: Dict, index: int) -> TTSSegment:
        """Process a single filtered segment into TTS-ready format.

        Creates a complete TTS segment with all necessary information for
        audio production and later video assembly.
        """
        # Create unique filename for this segment

        # Create speaker blocks for the conversation
        speaker_blocks = self.create_speaker_blocks(segment)

        # Compile metadata useful for video production
        metadata = {
            'original_id': segment['segment_id'],
            'engagement_score': segment['engagement_score'],
            'title': segment['title'],
            'duration_estimate': sum(len(block['text'].split()) / 2.5
                                     for block in speaker_blocks),  # Rough estimate
            'speaker_count': len(set(block['speaker'] for block in speaker_blocks))
        }

        return TTSSegment(
            segment_id=segment['segment_id'],
            speaker_blocks=speaker_blocks,
            metadata=metadata
        )

    def process_filtered_batch(self, batch_path: str) -> List[TTSSegment]:
        """Process an entire batch of filtered segments into TTS-ready format."""
        logging.info(f"Processing filtered batch: {batch_path}")

        # Load filtered segments
        with open(batch_path, 'r', encoding='utf-8') as f:
            filtered_segments = json.load(f)

        tts_segments = []
        for index, segment in enumerate(filtered_segments):
            try:
                tts_segment = self.process_segment(segment, index)
                tts_segments.append(tts_segment)
            except Exception as e:
                logging.error(f"Error processing segment {segment['segment_id']}: {str(e)}")
                continue

        logging.info(f"Processed {len(tts_segments)} segments for TTS")
        return tts_segments

    def save_tts_segments(self, segments: List[TTSSegment], batch_name: str):
        """Save TTS-ready segments for audio production.

        Saves both the processed text with speaker assignments and metadata
        needed for the subsequent audio production step.
        """
        output_path = Path(self.paths['processed']) / f"tts_ready_{batch_name}.json"

        # Convert to serializable format
        segments_data = [
            {
                'segment_id': seg.segment_id,
                'speaker_blocks': seg.speaker_blocks,
                'metadata': seg.metadata
            }
            for seg in segments
        ]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2)

        logging.info(f"Saved {len(segments)} TTS-ready segments to {output_path}")

