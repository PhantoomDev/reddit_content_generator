# src/generators/thumbnail_generator.py

import asyncio
import logging
from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageFont
import os
import re
from typing import Dict, Optional, Tuple, List
import aiofiles


class ThumbnailGenerator:
    def __init__(self, config: Dict):
        self.logger = logging.getLogger(__name__)
        self.config = config

        # Get paths from config
        content_paths = config['paths']
        self.images_path = Path(content_paths['images'])
        self.videos_path = Path(content_paths['videos'])

        # Set thumbnail dimensions
        self.width = 1920
        self.height = 1080

        # Load font
        self.font_path = self._get_system_font()

        # Keywords for image category matching
        self.category_keywords = {
            'general': {
                'learning': ['learn', 'study', 'school', 'university', 'education'],
                'facts': ['fact', 'statistics', 'number', 'percent', 'survey'],
                'history': ['history', 'war', 'ancient', 'century', 'years ago'],
                'science': ['science', 'research', 'study', 'discovered']
            },
            'tech': {
                'coding': ['code', 'program', 'software', 'developer', 'bug'],
                'gadgets': ['phone', 'computer', 'device', 'hardware'],
                'cybersecurity': ['security', 'hack', 'breach', 'cyber'],
                'ai': ['ai', 'artificial intelligence', 'machine learning', 'neural']
            },
            'pop': {
                'movies': ['movie', 'film', 'cinema', 'director', 'actor'],
                'gaming': ['game', 'gaming', 'player', 'console'],
                'tv': ['tv', 'television', 'show', 'series', 'episode'],
                'celebrities': ['celebrity', 'star', 'famous', 'actor', 'actress']
            }
        }

    def _get_system_font(self) -> str:
        """Get system font path based on OS."""
        if os.name == 'nt':  # Windows
            font_paths = [
                r'C:\Windows\Fonts\Arial.ttf',
                r'C:\Windows\Fonts\arial.ttf',
                os.path.expanduser('~\AppData\Local\Microsoft\Windows\Fonts\Arial.ttf')
            ]
        else:  # Unix-like
            font_paths = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/TTF/Arial.ttf',
                '/usr/share/fonts/liberation/LiberationSans-Regular.ttf'
            ]

        for path in font_paths:
            if os.path.exists(path):
                return path

        # Fallback to included font if possible
        fallback = Path(__file__).parent / 'assets' / 'Arial.ttf'
        if fallback.exists():
            return str(fallback)

        raise FileNotFoundError("No suitable font found. Please install Arial or include a fallback font.")

    def _process_thumbnail_text(self, text: str, max_words: int = 12) -> str:
        """
        Process thumbnail text to be more readable:
        - Limit total words
        - Remove unnecessary words
        - Format title case
        - Add ellipsis if truncated

        Args:
            text: Original text
            max_words: Maximum number of words to include

        Returns:
            Processed text suitable for thumbnail
        """
        # Remove common prefixes
        text = re.sub(r'^(TIL|TIL:|Today I Learned|Today I learned that)\s*', '', text, flags=re.IGNORECASE)

        # Split into words and limit length
        words = text.split()
        if len(words) > max_words:
            words = words[:max_words]
            # Add ellipsis if we truncated
            return ' '.join(words) + '...'

        return ' '.join(words)

    async def find_pending_thumbnails(self) -> List[Tuple[Path, Path]]:
        """
        Find all videos that need thumbnails by scanning for _thumbnail.txt files.

        Returns:
            List of tuples (info_file_path, output_thumbnail_path)
        """
        pending_thumbnails = []

        # Scan longform directory
        longform_base = self.videos_path / 'longform'
        if not longform_base.exists():
            return []

        # Walk through topic/date folders
        for info_file in longform_base.rglob('*_thumbnail.txt'):
            # Get the output thumbnail path by replacing _thumbnail.txt with _thumb.jpg
            thumbnail_path = info_file.parent / f"{info_file.stem.replace('_thumbnail', '')}_thumb.jpg"

            # Check if thumbnail already exists
            if not thumbnail_path.exists():
                pending_thumbnails.append((info_file, thumbnail_path))

        return pending_thumbnails

    async def _load_thumbnail_info(self, info_path: Path) -> str:
        """Load thumbnail text from info file."""
        async with aiofiles.open(info_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            return content.strip()

    def _get_topic_from_path(self, file_path: Path) -> str:
        """Extract topic from file path."""
        # Path structure: videos/longform/[topic]/[date]/...
        try:
            return file_path.parent.parent.name
        except Exception:
            return "general"  # Default to general if path structure is unexpected

    def _determine_image_category(self, text: str, topic: str) -> str:
        """Determine appropriate image category based on text content."""
        text = text.lower()

        # Get keywords for the topic
        topic_keywords = self.category_keywords.get(topic, {})

        # Count keyword matches for each category
        category_matches = {}
        for category, keywords in topic_keywords.items():
            matches = sum(1 for keyword in keywords if keyword in text)
            category_matches[category] = matches

        # Return category with most matches, or first category if no matches
        if category_matches:
            max_matches = max(category_matches.values())
            if max_matches > 0:
                return max(category_matches.items(), key=lambda x: x[1])[0]
            return list(topic_keywords.keys())[0]

        return "general"  # Fallback category

    def _get_random_image(self, topic: str, category: str) -> Optional[Path]:
        """Get random image from appropriate category folder."""
        image_dir = self.images_path / topic / category
        if not image_dir.exists():
            self.logger.warning(f"Image directory not found: {image_dir}")
            return None

        image_files = list(image_dir.glob('*.jpg')) + list(image_dir.glob('*.png'))
        if not image_files:
            self.logger.warning(f"No images found in {image_dir}")
            return None

        return random.choice(image_files)

    async def generate_thumbnail(self, info_path: Path, output_path: Path) -> None:
        """Generate thumbnail based on info file content."""
        try:
            # Load and process thumbnail text
            text = await self._load_thumbnail_info(info_path)
            text = self._process_thumbnail_text(text)

            # Get topic from file path
            topic = self._get_topic_from_path(info_path)

            # Create base image
            img = Image.new('RGB', (self.width, self.height), color='black')
            draw = ImageDraw.Draw(img)

            # Load and place category image (same as before)
            category = self._determine_image_category(text, topic)
            image_path = self._get_random_image(topic, category)
            if image_path:
                side_image = Image.open(image_path)
                target_width = self.width // 2
                aspect_ratio = side_image.width / side_image.height
                target_height = int(target_width / aspect_ratio)
                side_image = side_image.resize((target_width, target_height))
                y_offset = (self.height - target_height) // 2
                img.paste(side_image, (self.width // 2, y_offset))

            # Dynamic font sizing - start large and reduce if needed
            max_width = (self.width // 2) - 80  # Leave margins
            max_height = self.height - 80  # Leave margins
            font_size = 140  # Start larger

            while font_size > 60:  # Don't go smaller than 60
                font = ImageFont.truetype(self.font_path, font_size)

                # Split text into lines that fit width
                words = text.split()
                lines = []
                current_line = []

                for word in words:
                    test_line = ' '.join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    if bbox[2] < max_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]

                if current_line:
                    lines.append(' '.join(current_line))

                # Calculate total height needed
                line_height = font_size * 1.2  # Reduced line spacing
                total_height = len(lines) * line_height

                # If text fits height, we're good
                if total_height <= max_height and len(lines) <= 4:  # Limit to 4 lines
                    break

                # Otherwise reduce font size and try again
                font_size -= 10

            # Draw the text
            y_start = (self.height - (len(lines) * line_height)) // 2
            for i, line in enumerate(lines):
                y = y_start + (i * line_height)
                # Add slight shadow for better readability
                shadow_offset = 3
                draw.text((43, y + shadow_offset), line, font=font, fill='black')  # Shadow
                draw.text((40, y), line, font=font, fill='white')  # Main text

            # Save thumbnail
            img.save(output_path)
            self.logger.info(f"Generated thumbnail: {output_path}")

        except Exception as e:
            self.logger.error(f"Error generating thumbnail: {str(e)}")
            raise

    async def generate_all_pending(self) -> int:
        """
        Generate thumbnails for all pending videos.

        Returns:
            Number of thumbnails generated
        """
        pending = await self.find_pending_thumbnails()
        if not pending:
            self.logger.info("No pending thumbnails found")
            return 0

        self.logger.info(f"Found {len(pending)} pending thumbnails")

        # Generate thumbnails concurrently
        tasks = []
        for info_path, thumb_path in pending:
            tasks.append(self.generate_thumbnail(info_path, thumb_path))

        await asyncio.gather(*tasks)
        return len(pending)