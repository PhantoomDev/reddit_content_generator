# src/utils/config.py

import yaml
from pathlib import Path
from typing import Dict, Any


class ConfigManager:
    def __init__(self, config_path: str = "config/settings.yaml"):
        # Find the project root directory (where src/ is located)
        current_file = Path(__file__)  # Gets the location of config.py
        project_root = current_file.parent.parent.parent  # Go up from utils/config.py to project root

        # Create absolute path to config file
        self.config_path = project_root / config_path
        self.project_root = project_root

        # Load and process configuration
        self._config = self._load_config()
        self._resolve_paths()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found at {self.config_path}. "
                f"Working directory is {Path.cwd()}"
            )

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _resolve_paths(self):
        """Resolve all paths in the configuration relative to project root."""
        paths = self._config.get('paths', {})
        resolved_paths = {}

        for key, path in paths.items():
            # Convert string path to absolute path relative to project root
            resolved_paths[key] = str(self.project_root / path)

        # Update the config with resolved paths
        self._config['paths'] = resolved_paths

    @property
    def reddit_credentials(self) -> Dict[str, str]:
        """Get Reddit API credentials."""
        return self._config.get('reddit', {})

    @property
    def content_paths(self) -> Dict[str, str]:
        """Get content directory paths."""
        return self._config.get('paths', {})

    @property
    def scraping_settings(self) -> Dict[str, Any]:
        """Get scraping-specific settings."""
        return self._config.get('scraping', {})

    @property
    def processing_settings(self) -> Dict[str, Any]:
        """Get scraping-specific settings."""
        return self._config.get('processing', {})

    @property
    def filtering_settings(self) -> Dict[str, Any]:
        """Get filtering-specific settings."""
        return self._config.get('filtering', {})

    @property
    def tts_settings(self) -> Dict[str, Any]:
        """Get TTS-specific settings."""
        return self._config.get('tts_processing', {})

    @property
    def stock_footage(self) -> Dict[str, Any]:
        """Get stock-footage-specific settings."""
        return self._config.get('stock_footage', {})

    @property
    def video_generation_settings(self) -> Dict[str, Any]:
        """Get video_generation-specific settings."""
        return self._config.get('video_generation', {})

