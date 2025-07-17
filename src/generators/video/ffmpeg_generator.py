# src/generators/video/ffmpeg_generator.py

import subprocess
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import asyncio
import tempfile
import wave
import random
import shutil
import uuid


class FFmpegVideoGenerator:
    """
    Handles video generation using FFmpeg for both short-form and long-form content.
    This class provides a more reliable alternative to MoviePy by leveraging FFmpeg's
    robust video processing capabilities.
    """

    def __init__(self, config: Dict):
        # Configure logging first, so it's available to all methods
        self.logger = logging.getLogger(__name__)
        self.logger.debug("Initializing FFmpegVideoGenerator")

        self.config = config
        self.video_config = config['video_generation']

        # Use the properly resolved paths from content_paths instead of raw video_generation paths
        content_paths = config['paths']
        self.output_path = Path(content_paths['videos'])  # Use the resolved videos path
        self.temp_path = Path(content_paths['base_dir']) / 'temp'  # Create temp under base_dir
        self.stock_footage_path = Path(content_paths['base_dir']) / 'stock_footage'
        self.outro_path = Path(content_paths['base_dir']) / 'stock_footage' / 'fixed' / 'outro.wav'
        self.background_music_path = Path(content_paths['base_dir']) / 'music'

        self.logger.debug(f"Using output path: {self.output_path}")
        self.logger.debug(f"Using temp path: {self.temp_path}")
        self.logger.debug(f"Using stock footage path: {self.stock_footage_path}")

        # Initialize font path
        self.font_path = self._get_system_font()

        # Create directories after all paths are set up
        self._ensure_directories()

    async def _wait_for_file_completion(self, file_path: Path, timeout: float = 10.0) -> bool:
        """
        Wait for a file to be completely written and accessible.
        Returns True if file is ready, False if timeout reached.
        """
        start_time = asyncio.get_event_loop().time()
        last_size = -1

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if not file_path.exists():
                await asyncio.sleep(0.5)
                continue

            try:
                current_size = file_path.stat().st_size
                if current_size > 0 and current_size == last_size:
                    # File size hasn't changed for 0.5 seconds, likely finished writing
                    # Try to open it to verify accessibility
                    with open(file_path, 'rb') as f:
                        return True
                last_size = current_size
            except (OSError, PermissionError):
                pass

            await asyncio.sleep(0.5)

        return False

    async def _wait_for_file_release(self, file_path: Path, timeout: float = 5.0, check_interval: float = 0.1):
        """Wait for a file to be released by other processes."""
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            try:
                # Try to open the file in append mode
                with open(file_path, 'a'):
                    return True
            except PermissionError:
                await asyncio.sleep(check_interval)
        return False

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

    def _verify_ffmpeg(self):
        """Verify FFmpeg is installed and accessible."""
        try:
            # Use 'where' on Windows or 'which' on Unix to find ffmpeg
            if os.name == 'nt':  # Windows
                subprocess.run(['where', 'ffmpeg'], check=True, capture_output=True)
            else:  # Unix-like
                subprocess.run(['which', 'ffmpeg'], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "FFmpeg not found in system PATH. Please install FFmpeg and add it to your PATH."
            )

    def _ensure_directories(self):
        """Creates all necessary directories for video processing"""
        dirs_to_create = [
            self.output_path,
            self.temp_path,
            self.temp_path / 'segments',
            self.output_path / 'shorts',
            self.output_path / 'longform'
        ]

        for dir_path in dirs_to_create:
            dir_path.mkdir(parents=True, exist_ok=True)

    async def _run_ffmpeg_command(self, command: List[str], error_message: str,
                                  output_path: Optional[Path] = None) -> None:
        """Executes an FFmpeg command with improved error handling and file access checks."""
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                # If we're writing to a file, ensure it's not locked
                if output_path:
                    if output_path.exists():
                        # Wait for file to be released if it exists
                        if not await self._wait_for_file_release(output_path):
                            raise RuntimeError(f"Output file {output_path} is locked")

                # Create process
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                # Wait for completion and capture output
                stdout, stderr = await process.communicate()

                # Check for errors
                if process.returncode != 0:
                    error_output = stderr.decode() if stderr else "No error output available"
                    if attempt < max_retries - 1:
                        self.logger.warning(f"FFmpeg attempt {attempt + 1} failed: {error_output}")
                        await asyncio.sleep(retry_delay)
                        continue
                    raise RuntimeError(f"{error_message}: {error_output}")

                # Add a small delay after successful completion
                await asyncio.sleep(0.1)
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    await asyncio.sleep(retry_delay)
                else:
                    raise

    def wrap_text(self, text: str, max_width: int, font_size: int = 36) -> List[str]:
        """
        Wraps text to fit within a specified width, returning a list of lines.

        Args:
            text: The text to wrap
            max_width: Maximum width in pixels
            font_size: Font size in pixels

        Returns:
            List of lines, each fitting within max_width
        """
        # Approximate characters that fit in max_width
        # Using average character width of 0.6 times font size
        avg_char_width = font_size * 0.6
        chars_per_line = int(max_width / avg_char_width)

        blocks = text.splitlines()

        lines = []
        current_line = []
        current_length = 0

        for block in blocks:
            words = block.split()

            for word in words:
                word_length = len(word)

                # Add 1 for the space after the word
                if current_length + word_length + 1 <= chars_per_line:
                    current_line.append(word)
                    current_length += word_length + 1
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = word_length + 1

            # append extra empty line after \n
            lines.append(' '. join(current_line))
            current_line = []
            current_length = 0
            lines.append(' '.join(current_line))
        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def get_wav_duration(self, wav_path: Path) -> float:
        """Get accurate duration of a WAV file"""
        with wave.open(str(wav_path), 'rb') as wf:
            return wf.getnframes() / wf.getframerate()

    def get_total_wav_duration(self, wav_dir: Path) -> float:
        """Get total duration of all WAV files in a directory"""
        total_duration = 0
        for wav_file in sorted(wav_dir.glob('block_*.wav')):
            total_duration += self.get_wav_duration(wav_file)
        return total_duration

    def get_mp4_duration(self, video_path) -> float:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        return float(output)

    async def _generate_thumbnail_text(self, title: str) -> Dict[str, str]:
        """
        Generate thumbnail text and title for videos.

        Args:
            title: video segment title
            video_form: Either 'longform' or 'shorts'

        Returns:
            Dictionary with 'filename' and 'thumbnail_text' for longform,
            or just 'title' for shorts
        """

        # For shorts, just return a clean version of the title
        clean_title = title.replace('til', 'TIL').replace('TIL:', 'TIL')
        return {'title': clean_title}


    async def _save_thumbnail_info(self,
                                   output_dir: Path,
                                   base_name: str,
                                   thumbnail_info: Dict[str, str]) -> None:
        """
        Save thumbnail information to a text file.

        Args:
            output_dir: Directory where to save the text file
            base_name: Base name for the text file
            thumbnail_info: Dictionary containing thumbnail information
        """
        info_path = output_dir / f"{base_name}_thumbnail.txt"

        content = thumbnail_info['title']

        with open(info_path, 'w', encoding='utf-8') as f:
            f.write(content)

    async def generate_short(self,
                             audio_path: Path,
                             text_content: Dict,
                             output_path: Path) -> None:
        """
        Generates a vertical short-form video by:
        1. First creating segments with stock footage + audio
        2. Then adding text overlays
        3. Finally concatenating all segments

        Args:
            audio_path: Directory containing block_*.wav files
            text_content: Dict with title and text blocks
            output_path: Where to save final video
        """
        logger = logging.getLogger(__name__)

        # Create temp directory for processing
        with tempfile.TemporaryDirectory(dir=self.temp_path) as temp_dir:
            temp_dir_path = Path(temp_dir)

            try:
                # Generate thumbnail info
                thumbnail_info = await self._generate_thumbnail_text(
                    text_content['title']
                )

                # 1. Get audio blocks and calculate durations
                audio_blocks = sorted(list(audio_path.glob('block_*.wav')))
                text_blocks = text_content['text'].splitlines()
                total_duration = 0
                segment_duration = []
                for audio_file in audio_blocks:
                    with wave.open(str(audio_file), 'rb') as wf:
                        # Duration = number of frames / frame rate
                        duration = wf.getnframes() / wf.getframerate()
                        total_duration += duration
                        segment_duration.append(duration)

                # 2. Handle stock footage
                stock_footage = self._get_random_stock_footage(vertical=True)
                stock_footage_start = random.uniform(0, self.get_mp4_duration(stock_footage) - total_duration)

                music_file = self._get_random_background_music(total_duration)
                music_start = 0.0

                # Track segments for final concatenation
                segment_paths = []

                # 3. Process each block
                for i, (audio_block, text_block) in enumerate(zip(audio_blocks, text_blocks)):

                    # 4. Create base segment with stock footage and audio
                    base_segment = temp_dir_path / f"base_segment_{i:03d}.mp4"
                    await self._create_base_segment(
                        stock_footage=stock_footage,
                        audio_path=audio_block,
                        output_path=base_segment,
                        footage_start=stock_footage_start,
                        duration=segment_duration[i],
                        video_form='shorts'
                    )
                    stock_footage_start += segment_duration[i]

                    if not await self._wait_for_file_completion(base_segment):
                        logger.error(f"Timeout waiting for base segment {i} to complete")
                        continue

                        # Add a safety delay
                    await asyncio.sleep(1.0)

                    # 5. Add text overlay to base segment
                    text_segment = temp_dir_path / f"text_segment_{i:03d}.mp4"
                    await self._add_text_overlay(
                        input_path=base_segment,
                        text=text_block,
                        output_path=text_segment,
                        video_form='shorts'
                    )

                    # 6. Add background music
                    final_segment = temp_dir_path / f"final_segment_{i:03d}.mp4"
                    await self._add_background_music(
                        input_path=text_segment,
                        music_path=music_file,
                        output_path=final_segment,
                        music_start=music_start,
                        duration=segment_duration[i],
                        music_volume=self.video_config['audio']['background_music']['volume']
                    )
                    music_start += segment_duration[i]

                    segment_paths.append(str(final_segment))

                # 6. Create concat file
                concat_file = temp_dir_path / "concat.txt"
                with open(concat_file, 'w') as f:
                    for path in segment_paths:
                        f.write(f"file '{path}'\n")

                # 7. Final concatenation
                concat_cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-c:v', 'libx264',
                    '-preset', self.video_config['export'].get('preset', 'fast'),
                    '-b:v', self.video_config['export']['video_bitrate'],
                    '-c:a', 'aac',
                    '-b:a', self.video_config['export']['audio_bitrate'],
                    str(output_path)
                ]

                await self._run_ffmpeg_command(
                    concat_cmd,
                    "Failed to concatenate final video"
                )

                # Save thumbnail info
                await self._save_thumbnail_info(
                    output_path.parent,
                    output_path.stem,
                    thumbnail_info
                )

                logger.info(f"Successfully generated short video: {output_path}")

            except Exception as e:
                logger.error(f"Error generating short video: {str(e)}")
                raise

    async def generate_longform(self,
                                segments: List[Dict],
                                output_path: Path) -> None:
        """
        Generates a long-form video by:
        1. First creating all segments with stock footage + primary audio
        2. Concatenating all segments
        3. Adding continuous background music in a single pass
        4. Adding outro
        """
        logger = logging.getLogger(__name__)

        unique_id = str(uuid.uuid4())
        temp_dir_path = Path(self.temp_path) / f"debug_longform_{unique_id}"
        temp_dir_path.mkdir(parents=True, exist_ok=True)
        final_segments = []
        total_duration = 0

        try:
            if segments:
                first_segment = segments[0]

                thumbnail_info = await self._generate_thumbnail_text(
                    first_segment['text_content']['text']
                )
            # 1. Process each segment first without background music
            for i, segment in enumerate(segments):
                audio_base_path = Path(segment['audio_path'])
                audio_blocks = sorted(audio_base_path.parent.glob('block_*.wav'))
                text_blocks = segment['text_content']['text'].split('\n')

                for block_idx, (audio_block, text_block) in enumerate(zip(audio_blocks, text_blocks)):
                    block_duration = self.get_wav_duration(audio_block)

                    # Get appropriate stock footage
                    if (i == 0 and block_idx == 0) or footage_position - footage_start >= 20 or footage_position >= current_footage_duration:
                        current_footage = self._get_random_stock_footage(vertical=False)
                        current_footage_duration = self.get_mp4_duration(current_footage)
                        footage_position = random.uniform(0, current_footage_duration - block_duration)
                        footage_start = footage_position

                    # Generate base segment with stock footage and primary audio
                    base_segment = temp_dir_path / f"base_{i:03d}_{block_idx:03d}.mp4"
                    await self._create_base_segment(
                        stock_footage=current_footage,
                        audio_path=audio_block,
                        output_path=base_segment,
                        footage_start=footage_position,
                        duration=block_duration,
                        video_form='longform'
                    )

                    # Add text overlay
                    text_segment = temp_dir_path / f"text_{i:03d}_{block_idx:03d}.mp4"
                    await self._add_text_overlay(
                        input_path=base_segment,
                        text=text_block,
                        output_path=text_segment,
                        video_form='longform'
                    )

                    final_segments.append(str(text_segment))
                    footage_position += block_duration
                    total_duration += block_duration

            # 2. Process outro if needed
            temp_wav = os.path.join(temp_dir_path, f"temp_outro.wav")
            shutil.copy2(self.outro_path, temp_wav)
            current_footage = self._get_random_stock_footage(vertical=False)
            current_footage_duration = self.get_mp4_duration(current_footage)
            audio_block = Path(temp_wav)
            outro = temp_dir_path / f"base_outro.mp4"
            block_duration = self.get_wav_duration(audio_block)
            footage_position = random.uniform(0, current_footage_duration - block_duration)

            await self._create_base_segment(
                stock_footage=current_footage,
                audio_path=audio_block,
                output_path=outro,
                footage_start=footage_position,
                duration=block_duration,
                video_form='longform'
            )
            final_segments.append(str(outro))

            # 3. Create concat file with all segments including outro
            concat_file = temp_dir_path / "concat.txt"
            with open(concat_file, 'w') as f:
                for path in final_segments:
                    f.write(f"file '{path}'\n")

            # 4. Concatenate all segments and outro in one pass
            main_content = temp_dir_path / "main_content.mp4"
            concat_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c:v', 'libx264',
                '-preset', self.video_config['export'].get('preset', 'medium'),
                '-b:v', self.video_config['export']['video_bitrate'],
                '-r', str(self.video_config['longform']['fps']),
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac',
                '-b:a', self.video_config['export']['audio_bitrate'],
                '-ar', '48000',  # Consistent audio sample rate
                str(main_content)
            ]

            await self._run_ffmpeg_command(concat_cmd, "Failed to concatenate segments and outro")

            # Calculate total duration including outro for music
            total_duration = self.get_mp4_duration(main_content)

            # 5. Prepare concatenated background music that covers the full duration
            music_concat_file = temp_dir_path / "music_concat.txt"
            concatenated_music = temp_dir_path / "concatenated_music.wav"

            # Calculate how many music tracks we need
            current_music_duration = 0
            music_files = []

            with open(music_concat_file, 'w') as f:
                while current_music_duration < total_duration:
                    music_file = self._get_random_background_music(total_duration - current_music_duration)
                    music_duration = self.get_mp4_duration(music_file)
                    f.write(f"file '{music_file}'\n")
                    music_files.append(music_file)
                    current_music_duration += music_duration

            # Concatenate music files
            music_concat_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(music_concat_file),
                '-c:a', 'pcm_s16le',  # Use WAV format for accurate concatenation
                str(concatenated_music)
            ]
            await self._run_ffmpeg_command(music_concat_cmd, "Failed to concatenate music files")

            # 5. Add continuous background music in single pass
            with_music = temp_dir_path / "with_music.mp4"
            music_cmd = [
                'ffmpeg',
                '-i', str(main_content),
                '-i', str(concatenated_music),
                '-filter_complex',
                f'[1:a]volume={self.video_config["audio"]["background_music"]["volume"]}[music];'
                '[0:a][music]amix=inputs=2:duration=first[a]',
                '-map', '0:v',
                '-map', '[a]',
                '-c:v', 'copy',
                '-shortest',
                str(with_music)
            ]
            await self._run_ffmpeg_command(music_cmd, "Failed to add background music")

            # 6. Copy final video to output path
            shutil.copy2(str(with_music), str(output_path))

            # Save thumbnail info
            await self._save_thumbnail_info(
                output_path.parent,
                output_path.stem,
                thumbnail_info
            )

        except Exception as e:
            logger.error(f"Error generating longform video: {str(e)}")
            raise

    async def _create_base_segment(self,
                                   stock_footage: Path,
                                   audio_path: Path,
                                   output_path: Path,
                                   footage_start: float,
                                   duration: float,
                                   video_form: str = 'shorts') -> None:
        """
        Creates a video segment with stock footage and audio.
        Handles scaling and cropping of stock footage appropriately for both vertical and horizontal formats.
        """
        # Get target dimensions
        target_width = self.video_config[video_form]["width"]
        target_height = self.video_config[video_form]["height"]

        # Different scaling approach based on video format
        if video_form == 'shorts':
            # For vertical videos (shorts), scale to width and crop height
            scale_filter = f'scale={target_width}:-1'
            crop_filter = f'crop={target_width}:{target_height}'
        else:
            # For horizontal videos (longform), maintain aspect ratio with padding if needed
            scale_filter = f'scale={target_width}:-2'  # -2 maintains even height
            crop_filter = f'crop={target_width}:{target_height}:0:0'

        command = [
            'ffmpeg',
            '-ss', str(footage_start),
            '-i', str(stock_footage),
            '-i', str(audio_path),
            '-filter_complex',
            f'[0:v]{scale_filter},{crop_filter}[v]',
            '-map', '[v]',
            '-map', '1:a',
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-c:a', 'aac',
            str(output_path)
        ]

        await self._run_ffmpeg_command(
            command,
            f"Failed to create base segment: {output_path.name}"
        )

        await asyncio.sleep(0.2)

    async def _add_text_overlay(self,
                                input_path: Path,
                                text: str,
                                output_path: Path,
                                video_form: str = 'shorts') -> Path:
        """
        Adds text overlay to a video segment with semi-transparent background.
        Includes text wrapping and proper vertical positioning of multiple lines.
        """
        # Get video dimensions for text wrapping
        max_width = self.video_config[video_form]['width']
        font_size = self.video_config[video_form]['text_settings']['font_size']
        height = self.video_config[video_form]['height']

        # Wrap text into lines
        wrapped_lines = self.wrap_text(
            text,
            max_width=int(max_width * 0.8),  # Use 80% of video width
            font_size=font_size
        )

        # Calculate text box height based on number of lines
        line_height = int(font_size * 1.5)  # 1.5x font size for comfortable line spacing
        text_box_height = len(wrapped_lines) * line_height
        start_y = (height - text_box_height) // 2

        try:
            # Create temporary files for each line
            temp_files = []
            drawtext_filters = []

            for i, line in enumerate(wrapped_lines):
                # Create temp file for this line
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                                 delete=False, encoding='utf-8') as temp_file:
                    temp_file.write(line)
                    temp_files.append(Path(temp_file.name))

                    # Convert paths for FFmpeg
                    font_path = str(self.font_path).replace('\\', '/').replace(':', r'\:')
                    text_file_path = str(temp_file.name).replace('\\', '/').replace(':', r'\:')

                    # Calculate Y position for this line
                    y_pos = start_y + (i * line_height)

                    # Create drawtext filter for this line
                    filter_text = (
                        f"drawtext=fontfile='{font_path}'"
                        f":textfile='{text_file_path}'"
                        f":fontsize={font_size}"
                        f":fontcolor=white"
                        f":x=(w-text_w)/2"
                        f":y={y_pos}"
                        f":box=1"
                        f":boxcolor=black@0.8"
                        f":boxborderw=5"
                    )
                    drawtext_filters.append(filter_text)

            # Combine all text drawing filters
            combined_filters = ','.join(drawtext_filters)

            # FFmpeg command to add all text lines
            command = [
                'ffmpeg',
                '-i', str(input_path),
                '-vf', combined_filters,
                '-c:a', 'copy',
                str(output_path)
            ]

            await self._run_ffmpeg_command(
                command,
                f"Failed to add text overlay: {output_path.name}"
            )

        finally:
            # Clean up all temporary files
            for temp_file in temp_files:
                try:
                    temp_file.unlink()
                except Exception as e:
                    logging.warning(f"Failed to clean up temp file {temp_file}: {str(e)}")

        return output_path

    async def _add_background_music(self,
                                    input_path: Path,
                                    music_path: Path,
                                    output_path: Path,
                                    music_start: float,
                                    duration: float,
                                    music_volume: float = 0.1) -> None:
        """
        Adds background music to a video segment.

        Args:
            input_path: Path to input video with existing audio
            music_path: Path to background music file
            output_path: Path to save the output video
            music_start: Start time in the music file
            duration: Duration of the segment
            music_volume: Volume level for background music (0.0 to 1.0)
        """
        command = [
            'ffmpeg',
            '-i', str(input_path),  # Input 0: Video with existing audio
            '-ss', str(music_start),
            '-i', str(music_path),  # Input 1: Background music
            '-filter_complex',
            # Mix the original audio with background music
            f'[1:a]volume={music_volume}[music];'  # Adjust music volume
            '[0:a][music]amix=inputs=2:duration=first[a]',  # Mix both audio streams
            '-map', '0:v',  # Keep original video
            '-map', '[a]',  # Use mixed audio
            '-t', str(duration),  # Set duration
            '-c:v', 'copy',  # Copy video codec to speed up processing
            '-c:a', 'aac',  # Audio codec
            '-b:a', self.video_config['export']['audio_bitrate'],
            str(output_path)
        ]

        await self._run_ffmpeg_command(
            command,
            f"Failed to add background music to segment: {output_path.name}"
        )

    async def _generate_outro(self, temp_dir: Path, video_form: str = 'longform') -> Path:
        """Generate a simple outro with black background and audio"""
        width = self.video_config[video_form]['width']
        height = self.video_config[video_form]['height']
        fps = self.video_config[video_form]['fps']
        outro_duration = 5  # 5 seconds outro

        # Output path
        processed_outro = temp_dir / "processed_outro.mp4"

        # Command to generate black video with audio
        command = [
            'ffmpeg',
            # Generate black video
            '-f', 'lavfi',
            '-i', f'color=c=black:s={width}x{height}:r={fps}',
            # Add the TTS audio
            '-i', str(self.outro_path),
            '-shortest',  # Match video length to audio
            '-c:v', 'libx264',
            '-tune', 'stillimage',  # Optimize for static image
            '-preset', self.video_config['export'].get('preset', 'medium'),
            '-b:v', self.video_config['export']['video_bitrate'],
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', self.video_config['export']['audio_bitrate'],
            '-ar', '48000',
            str(processed_outro)
        ]

        await self._run_ffmpeg_command(command, "Failed to generate outro")

        return processed_outro

    def _get_random_stock_footage(self, category: Optional[str] = None, vertical=True) -> Path:
        """
        Selects appropriate stock footage for video background.
        This method ensures we get footage that matches our video type and theme.

        Args:
            category: Optional category to select from (e.g., 'gaming', 'satisfying')

        Returns:
            Path to selected stock footage file
        """
        # Get the base stock footage directory
        stock_base = self.stock_footage_path

        # If no category specified, choose from available categories
        if category is None:
            categories = list(self.video_config['stock_footage']['categories'].keys())
            category = random.choice(categories)

        # Get all videos in the category's vertical folder
        if vertical:
            category_path = stock_base / category / 'vertical'
        else:
            category_path = stock_base / category / 'horizontal'
        video_files = list(category_path.glob('*.mp4'))

        if not video_files:
            raise FileNotFoundError(
                f"No stock footage found in category: {category}, {category_path}"
            )

        return random.choice(video_files)

    def _get_random_background_music(self, duration: float) -> Path:
        """
        Selects a random background music file and a random start point.

        Args:
            duration: Required duration of music segment

        Returns:
            Tuple containing (music_file_path, start_time)
        """
        # Get the base music directory
        music_base = self.background_music_path

        # Get all music files
        music_files = list(music_base.glob('*.mp3'))
        if not music_files:
            raise FileNotFoundError("No background music files found")

        # Select random music file
        music_file = random.choice(music_files)

        return music_file

