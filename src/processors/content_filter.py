# src/processors/content_filter.py

from pathlib import Path
import json
import logging
from typing import List, Dict, Any
from dataclasses import dataclass
import re
from datetime import datetime


@dataclass
class FilteredSegment:
    """Represents a filtered conversation segment ready for video production"""
    segment_id: str
    title: str
    comments: List[Dict[str, Any]]
    engagement_score: float


class ContentFilter:
    def __init__(self, config):
        """Initialize the content filter using configuration manager"""
        # Store paths from config
        self.paths = config.content_paths

        # Get filtering settings
        filtering_settings = config.filtering_settings
        criteria = filtering_settings.get('criteria', {})

        # Initialize filtering criteria with defaults if not in config
        self.min_text_length = criteria.get('min_text_length', 20)
        self.max_text_length = criteria.get('max_text_length', 500)
        self.max_title_length = criteria.get('max_title_length', 300)
        self.min_line_length = criteria.get('min_line_length', 5)
        self.max_line_breaks = criteria.get('max_line_breaks', 5)
        self.min_score = criteria.get('min_score', 100)
        self.min_post_score = criteria.get('min_post_score', 1000)
        self.min_quality_score = criteria.get('min_quality_score', 0.4)
        self.max_replies = criteria.get('max_replies', 3)
        self.max_depth = criteria.get('max_depth', 2)
        self.min_comments = criteria.get('min_comments', 2)
        self.max_comments = criteria.get('max_comments', 5)

        # Get content filters
        content_filters = filtering_settings.get('content_filters', {})
        self.excluded_phrases = content_filters.get('excluded_phrases', [])
        self.excluded_topics = content_filters.get('excluded_topics', [])

        # Quality scoring weights
        quality_weights = filtering_settings.get('quality_weights', {})
        self.engagement_weight = quality_weights.get('engagement', 0.4)
        self.length_weight = quality_weights.get('length', 0.2)
        self.formatting_weight = quality_weights.get('formatting', 0.2)
        self.variety_weight = quality_weights.get('variety', 0.2)

        # Output settings
        output_settings = filtering_settings.get('output', {})
        self.max_segments = output_settings.get('max_segments_per_batch', 50)
        self.min_segment_gap = output_settings.get('min_segment_gap', 3600)

        # Setup logging
        self._setup_logging()

        # Create necessary directories
        self.create_directory_structure()

    def _setup_logging(self):
        """Configure detailed logging for debugging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

        # Add file handler for debugging
        debug_log = Path(self.paths['filtered']).parent / 'filter_debug.log'
        fh = logging.FileHandler(debug_log)
        fh.setLevel(logging.DEBUG)
        logging.getLogger('').addHandler(fh)

    def create_directory_structure(self):
        """Create the necessary directory structure for filtered content"""
        filtered_path = Path(self.paths['filtered'])
        filtered_path.mkdir(parents=True, exist_ok=True)

    def calculate_text_quality(self, text: str) -> float:
        """Calculate quality score for text content based on multiple factors"""
        if not text or len(text) < self.min_text_length:
            return 0.0

        # Length score
        length_score = min(len(text) / self.max_text_length, 1.0)

        # Formatting score
        lines = text.split('\n')
        formatted_lines = sum(1 for line in lines if len(line.strip()) >= self.min_line_length)
        formatting_score = formatted_lines / max(len(lines), 1)

        # Variety score (check for repetition and common phrases)
        words = text.lower().split()
        unique_words = len(set(words))
        variety_score = unique_words / max(len(words), 1)

        # Check for excluded content
        if any(phrase.lower() in text.lower() for phrase in self.excluded_phrases):
            return 0.0

        # Calculate weighted score
        quality_score = (
                length_score * self.length_weight +
                formatting_score * self.formatting_weight +
                variety_score * self.variety_weight
        )

        return min(max(quality_score, 0.0), 1.0)

    def is_good_text(self, text: str) -> bool:
        """Check if text is suitable for video content based on configured criteria"""
        # Basic length checks
        if not text or len(text) < self.min_text_length:
            return False
        if len(text) > self.max_text_length:
            return False

        # Line break check
        if text.count('\n') > self.max_line_breaks:
            return False

        # Content checks
        if any(phrase.lower() in text.lower() for phrase in self.excluded_phrases):
            return False

        # Topic filtering
        if any(topic.lower() in text.lower() for topic in self.excluded_topics):
            return False

        # Calculate quality score
        quality_score = self.calculate_text_quality(text)
        return quality_score >= self.min_quality_score

    def is_good_chain(self, chain: Dict) -> bool:
        """Determine if a comment chain would make good video content"""
        # Check main comment quality and score
        if not self.is_good_text(chain['text']):
            return False
        if chain.get('score', 0) < self.min_score:
            return False

        # Check quality score
        if chain.get('quality_score', 0) < self.min_quality_score:
            return False

        # Process replies if present
        replies = chain.get('replies', [])
        if replies:
            good_replies = [
                r for r in replies[:self.max_depth]
                if self.is_good_text(r['text']) and
                   r.get('score', 0) >= self.min_score and
                   r.get('quality_score', 0) >= self.min_quality_score
            ]

            # Check if we have enough quality replies
            if not (1 <= len(good_replies) <= self.max_replies):
                return False

        return True

    def clean_chain(self, chain: Dict) -> Dict:
        """Clean a comment chain to retain only necessary information"""
        cleaned = {
            'text': chain['text'],
            'score': chain.get('score', 0),
            'quality_score': chain.get('quality_score', 0),
            'replies': []
        }

        # Only include quality replies
        for reply in chain.get('replies', [])[:self.max_replies]:
            if self.is_good_text(reply['text']):
                cleaned['replies'].append({
                    'text': reply['text'],
                    'score': reply.get('score', 0),
                    'quality_score': reply.get('quality_score', 0)
                })

        return cleaned

    def process_batch(self, batch_path: str) -> List[FilteredSegment]:
        """Process a batch of Reddit content and filter good segments"""
        logging.info(f"Processing batch: {batch_path}")

        with open(batch_path, 'r', encoding='utf-8') as f:
            posts = json.load(f)

        filtered_segments = []

        # Process each post
        for post in posts:
            # Basic post filtering
            if post['score'] < self.min_post_score:
                continue

            title = post['title'].lower()
            if len(title) > self.max_title_length:
                continue

            # Skip excluded topics
            if any(topic in title for topic in self.excluded_topics):
                continue

            good_chains = []

            # First collect all good comment chains for this post
            for chain in post['comment_chains']:
                if self.is_good_chain(chain):
                    cleaned_chain = self.clean_chain(chain)
                    good_chains.append(cleaned_chain)

            # If we found enough good chains for this post, create a segment
            if self.min_comments <= len(good_chains) <= self.max_comments:
                segment = FilteredSegment(
                    segment_id=post['id'],
                    title=title,
                    comments=good_chains,
                    engagement_score=post['engagement_score']
                )
                filtered_segments.append(segment)

        # Sort by engagement score and limit output
        filtered_segments.sort(key=lambda x: x.engagement_score, reverse=True)
        filtered_segments = filtered_segments[:self.max_segments]

        logging.info(
            f"Found {len(filtered_segments)} good segments from {len(posts)} posts"
        )
        return filtered_segments

    def save_filtered_segments(self, segments: List[FilteredSegment], batch_name: str):
        """Save filtered segments to JSON file using configured paths"""
        output_path = Path(self.paths['filtered']) / f"filtered_{batch_name}.json"

        segments_data = [
            {
                'segment_id': seg.segment_id,
                'title': seg.title,
                'comments': seg.comments,
                'engagement_score': seg.engagement_score
            }
            for seg in segments
        ]

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(segments_data, f, indent=2)

        logging.info(f"Saved {len(segments)} filtered segments to {output_path}")