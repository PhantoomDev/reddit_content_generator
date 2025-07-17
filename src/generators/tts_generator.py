# src/generators/tts_generator.py

from pathlib import Path
import json
import logging
from typing import List, Dict, Any
import pyttsx3
import pythoncom
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
import threading
import queue
import time

from src.utils.config import ConfigManager


@dataclass
class TTSRequest:
    """Represents a single TTS request with all necessary information for processing"""
    text: str
    speaker: str
    output_path: str
    segment_id: str
    block_index: int


class TTSWorker:
    """Handles TTS generation in a single thread with proper resource management"""

    def __init__(self, voice_properties: Dict):
        """Initialize a TTS worker with voice properties"""
        self.voice_properties = voice_properties
        self.engine = None
        # Thread-local storage for COM initialization state
        self._thread_local = threading.local()

    def _ensure_com_initialized(self):
        """Ensures COM is initialized for the current thread"""
        if not hasattr(self._thread_local, 'com_initialized'):
            pythoncom.CoInitialize()
            self._thread_local.com_initialized = True

    def initialize_engine(self):
        """Creates and configures a new TTS engine instance"""
        # Ensure COM is initialized before creating engine
        self._ensure_com_initialized()

        if self.engine is None:
            self.engine = pyttsx3.init()

    def cleanup(self):
        """Properly clean up resources"""
        if hasattr(self._thread_local, 'com_initialized'):
            if self.engine:
                try:
                    self.engine.stop()
                except:
                    pass
                self.engine = None
            pythoncom.CoUninitialize()
            del self._thread_local.com_initialized

    def generate_audio(self, request: TTSRequest) -> str:
        """Generate audio for a single text segment with verification"""
        try:
            self.initialize_engine()

            # Configure voice properties
            props = self.voice_properties[request.speaker]
            self.engine.setProperty('rate', props['rate'])
            self.engine.setProperty('volume', props['volume'])

            # Set voice
            voices = self.engine.getProperty('voices')
            self.engine.setProperty('voice', voices[0].id)

            # Ensure output directory exists
            output_path = Path(request.output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Generate audio
            self.engine.save_to_file(request.text, str(output_path))
            self.engine.runAndWait()

            # Wait for file to be fully written and verify its existence
            max_retries = 10  # Increased from 5
            base_delay = 0.2
            for attempt in range(max_retries):
                # Generate audio if this is the first attempt or if previous attempt failed
                if attempt == 0:
                    self.engine.save_to_file(request.text, str(output_path))
                    self.engine.runAndWait()

                # Exponential backoff for retry delays
                current_delay = base_delay * (2 ** attempt)

                # Wait for the delay period
                time.sleep(current_delay)

                try:
                    # Comprehensive file verification
                    if output_path.exists():
                        # Try to open the file to ensure it's not locked
                        with open(output_path, 'rb') as f:
                            # Read a small chunk to verify file integrity
                            first_bytes = f.read(1024)
                            if len(first_bytes) > 0:
                                # Successful verification
                                return request.output_path
                except (IOError, OSError) as e:
                    # Log the specific error but continue retrying
                    logging.debug(f"Retry {attempt + 1}/{max_retries} for {output_path}: {str(e)}")
                    continue

            # If we get here, all retries failed
            # Instead of raising an exception, we could optionally retry the entire generation
            logging.warning(f"File verification timed out for {output_path}, attempting regeneration")
            return self.generate_audio(request)  # Recursive retry of the entire generation

        except Exception as e:
            raise Exception(f"TTS generation failed: {str(e)}")


class TTSGenerator:
    """Manages parallel TTS generation with proper resource handling"""

    def __init__(self, config: ConfigManager):
        self.config = config
        self.audio_output_path = Path(config.content_paths['audio'])
        self.processed_path = Path(config.content_paths['processed'])
        self.tts_settings = config.tts_settings

        # Ensure directories exist
        self.audio_output_path.mkdir(parents=True, exist_ok=True)

        # Configure logging
        self.logger = logging.getLogger(__name__)

        # Worker pool configuration
        self.max_workers = self.tts_settings['generator_max_worker']

        # Voice configuration
        self.voice_properties = {
            'narrator': {'rate': 150, 'volume': 0.9, 'voice': 'english'},
            'commenter': {'rate': 175, 'volume': 1.0, 'voice': 'english'},
            'replier': {'rate': 160, 'volume': 0.95, 'voice': 'english'}
        }

        # Create a pool of worker threads
        self.workers = []
        for _ in range(self.max_workers):
            worker = TTSWorker(self.voice_properties)
            self.workers.append(worker)

    def cleanup_workers(self):
        """Clean up all worker threads"""
        for worker in self.workers:
            try:
                worker.cleanup()
            except:
                pass

    def process_speaker_blocks(self, segment: Dict[str, Any], batch_id: str) -> List[str]:
        """Process all speaker blocks for a segment using the worker pool"""
        segment_dir = self.audio_output_path / batch_id / segment['segment_id']
        audio_files = []

        # Create requests for all blocks
        requests = []
        for i, block in enumerate(segment['speaker_blocks']):
            output_path = segment_dir / f"block_{i:03d}.wav"
            request = TTSRequest(
                text=block['text'],
                speaker=block['speaker'],
                output_path=str(output_path),
                segment_id=segment['segment_id'],
                block_index=i
            )
            requests.append(request)

        # Process requests using thread pool
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Create a queue for available workers
            worker_queue = queue.Queue()
            for worker in self.workers:
                worker_queue.put(worker)

            def process_with_worker(request):
                worker = worker_queue.get()
                try:
                    result = worker.generate_audio(request)
                    self.logger.info(f"Generated audio for segment {request.segment_id}, block {request.block_index}")
                    return result
                finally:
                    worker_queue.put(worker)

            # Submit all requests
            future_to_request = {
                executor.submit(process_with_worker, request): request
                for request in requests
            }

            # Collect results
            for future in as_completed(future_to_request):
                request = future_to_request[future]
                try:
                    audio_path = future.result()
                    audio_files.append(audio_path)
                except Exception as e:
                    self.logger.error(f"Failed to generate audio for block {request.block_index}: {str(e)}")

        return audio_files

    def process_batch(self, batch_file: Path) -> Dict[str, Any]:
        """Process an entire batch of TTS-ready segments"""
        try:
            batch_id = batch_file.stem.replace('tts_ready_', '')

            with open(batch_file, 'r') as f:
                segments = json.load(f)

            batch_results = {
                'batch_id': batch_id,
                'timestamp': datetime.now().isoformat(),
                'segments': []
            }

            for segment in segments:
                try:
                    audio_files = self.process_speaker_blocks(segment, batch_id)

                    batch_results['segments'].append({
                        'segment_id': segment['segment_id'],
                        'audio_files': audio_files,
                        'metadata': segment['metadata']
                    })

                    self.logger.info(f"Processed segment {segment['segment_id']}")

                except Exception as e:
                    self.logger.error(f"Error processing segment {segment['segment_id']}: {str(e)}")
                    continue

            return batch_results

        except Exception as e:
            self.logger.error(f"Error processing batch {batch_file}: {str(e)}")
            raise

    def process_all_pending(self) -> List[Dict[str, Any]]:
        """Process all pending TTS-ready files"""
        try:
            pending_files = list(self.processed_path.glob('tts_ready_*.json'))

            if not pending_files:
                self.logger.info("No pending TTS files found")
                return []

            self.logger.info(f"Found {len(pending_files)} pending TTS batches")

            results = []
            for file in pending_files:
                try:
                    result = self.process_batch(file)
                    results.append(result)
                    self.logger.info(f"Successfully processed batch {file.name}")
                except Exception as e:
                    self.logger.error(f"Failed to process batch {file.name}: {str(e)}")
                    continue

            return results

        finally:
            # Always clean up workers
            self.cleanup_workers()

