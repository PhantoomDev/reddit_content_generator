# src/scripts/scrape.py

import logging
import asyncio
from pathlib import Path
import json
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
import sys
from src.utils.config import ConfigManager
from src.scrapers.reddit_scraper import RedditContentScraper


class ParallelScrapingManager:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.scraper = RedditContentScraper(config)
        self.max_worker = config.scraping_settings['max_worker_main']
        self.executor = ThreadPoolExecutor(max_workers=self.max_worker)

        # Enhanced logging setup
        self._setup_logging()

    def _setup_logging(self):
        """Setup detailed logging with both file and console handlers"""
        # Create a formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
        )

        # Setup file handler for detailed debugging
        log_path = Path(self.config.content_paths['raw']).parent / 'scraper_debug.log'
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # Setup console handler for basic info
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        root_logger.handlers = []  # Clear existing handlers
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        logging.debug("Logging system initialized")

    async def scrape_subreddit_wrapper(self, category: str, subreddit: str) -> Dict:
        """Wrapper for subreddit scraping with enhanced error tracking"""
        logging.debug(f"Starting scrape wrapper for {category}/r/{subreddit}")
        try:
            logging.info(f"Initiating scrape for {category}/r/{subreddit}")

            # Use run_in_executor for blocking Reddit API calls
            loop = asyncio.get_running_loop()
            posts = await loop.run_in_executor(
                self.executor,
                self.scraper.scrape_subreddit,
                subreddit,
                self.config.scraping_settings['default_post_limit'],
            )

            logging.debug(f"Retrieved {len(posts)} posts for {subreddit}")

            if not posts:
                raise ValueError(f"No posts retrieved for {subreddit}")

            # Save batch
            batch_name = f"batch_{category}_{subreddit}"
            batch_id = await loop.run_in_executor(
                self.executor,
                self.scraper.save_batch,
                posts,
                batch_name
            )

            logging.info(f"Successfully completed scraping for {category}/r/{subreddit}")
            return {
                "category": category,
                "subreddit": subreddit,
                "batch_id": batch_id,
                "status": "success",
                "post_count": len(posts)
            }

        except Exception as e:
            logging.error(f"Error in scrape wrapper for {category}/r/{subreddit}: {str(e)}",
                          exc_info=True)
            return {
                "category": category,
                "subreddit": subreddit,
                "batch_id": None,
                "status": "error",
                "error": f"{type(e).__name__}: {str(e)}"
            }

    async def scrape_all_parallel(self) -> List[str]:
        """Coordinate parallel scraping of all subreddits"""
        logging.debug("Starting parallel scraping coordination")
        subreddits = self.config.scraping_settings['subreddits']
        scraping_tasks = []

        # Create tasks for each subreddit
        for category, subreddit_list in subreddits.items():
            logging.debug(f"Creating tasks for category: {category}")
            for subreddit in subreddit_list:
                logging.debug(f"Adding task for {category}/r/{subreddit}")
                task = self.scrape_subreddit_wrapper(category, subreddit)
                scraping_tasks.append(task)

        # Run tasks concurrently
        logging.debug(f"Starting concurrent execution of {len(scraping_tasks)} tasks")
        results = await asyncio.gather(*scraping_tasks, return_exceptions=True)

        # Process results
        successful_batches = []
        for result in results:
            if isinstance(result, Exception):
                logging.error(f"Task failed with exception: {str(result)}")
                continue

            if result["status"] == "success":
                successful_batches.append(result["batch_id"])
                logging.debug(f"Successfully processed {result['subreddit']}")
            else:
                logging.warning(f"Failed to process {result['subreddit']}: {result['error']}")

        # Save manifest
        manifest_path = Path(self.config.content_paths['metadata']) / "latest_batch_manifest.json"
        manifest_data = {'batches': successful_batches}

        logging.debug(f"Saving manifest with {len(successful_batches)} successful batches")
        with open(manifest_path, 'w') as f:
            json.dump(manifest_data, f)

        return successful_batches


def scrape_content() -> List[str]:
    """Coordinated entry point for parallel scraping"""
    logging.info("Initializing parallel scraping process")

    config = ConfigManager()
    scraper_manager = ParallelScrapingManager(config)

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        logging.debug("Starting event loop for parallel scraping")
        result = loop.run_until_complete(scraper_manager.scrape_all_parallel())
        logging.info(f"Completed parallel scraping with {len(result)} successful batches")
        return result

    except Exception as e:
        logging.error(f"Critical error in scraping process: {str(e)}", exc_info=True)
        return []

    finally:
        logging.debug("Cleaning up event loop")
        loop.close()


if __name__ == "__main__":
    scrape_content()
