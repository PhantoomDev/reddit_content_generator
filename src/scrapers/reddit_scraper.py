# src/scrapers/reddit_scraper.py

from pathlib import Path
from typing import List, Dict
import logging
import json
import asyncio
import random
from datetime import datetime
import praw
from concurrent.futures import ThreadPoolExecutor


class RedditContentScraper:
    def __init__(self, config):
        """Initialize scraper while maintaining original config structure"""
        # Keep original initialization
        credentials = config.reddit_credentials
        self.reddit = praw.Reddit(
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            user_agent=credentials['user_agent']
        )
        self.paths = config.content_paths
        self.scraping_settings = config.scraping_settings
        self.post_settings = self.scraping_settings['post_settings']
        self.comment_settings = self.scraping_settings['comment_settings']
        self.weights = self.scraping_settings['engagement_weights']
        self.time_windows = self.scraping_settings['time_windows']
        self.worker_count = self.scraping_settings['max_worker_sub']

        # Add new optimization-related attributes
        self.executor = ThreadPoolExecutor(max_workers=self.worker_count)
        self._setup_logging()
        self.create_directory_structure()

    def _setup_logging(self):
        """Configure detailed logging for debugging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        # Add file handler for debugging
        debug_log = Path(self.paths['raw']).parent / 'scraper_debug.log'
        fh = logging.FileHandler(debug_log)
        fh.setLevel(logging.DEBUG)
        logging.getLogger('').addHandler(fh)

    async def _get_posts_async(self, subreddit, time_filter: str, limit: int):
        """Asynchronously fetch posts with enhanced variety"""
        try:
            loop = asyncio.get_event_loop()
            sort_method = self._get_random_sort_method()

            # Fetch more posts than needed to allow for filtering
            fetch_limit = limit * 3

            # Use different sorting methods
            if sort_method == 'hot':
                posts = await loop.run_in_executor(
                    self.executor,
                    lambda: list(subreddit.hot(limit=fetch_limit))
                )
            elif sort_method == 'top':
                posts = await loop.run_in_executor(
                    self.executor,
                    lambda: list(subreddit.top(time_filter=time_filter, limit=fetch_limit))
                )
            elif sort_method == 'rising':
                posts = await loop.run_in_executor(
                    self.executor,
                    lambda: list(subreddit.rising(limit=fetch_limit))
                )
            else:  # new
                posts = await loop.run_in_executor(
                    self.executor,
                    lambda: list(subreddit.new(limit=fetch_limit))
                )

            # Add some randomization to post selection
            if len(posts) > limit:
                posts = random.sample(posts, limit)

            logging.debug(f"Retrieved {len(posts)} posts using {sort_method} sort")
            return posts

        except Exception as e:
            logging.error(f"Error fetching posts: {str(e)}")
            return []

    async def _process_comments_async(self, post, max_comments=3):
        """Process comments asynchronously with detailed logging"""
        try:
            loop = asyncio.get_event_loop()

            # Load comments efficiently
            logging.debug(f"Loading comments for post {post.id}")
            await loop.run_in_executor(
                self.executor,
                lambda: post.comments.replace_more(limit=0)
            )

            comment_chains = []
            processed = 0

            for comment in list(post.comments)[:max_comments * 2]:
                if not isinstance(comment, praw.models.Comment):
                    continue

                if (len(comment.body) < self.comment_settings['min_comment_length'] or
                        comment.body in ["[removed]", "[deleted]"]):
                    continue

                chain = {
                    "id": comment.id,
                    "text": comment.body,
                    "score": comment.score,
                    "created_utc": comment.created_utc,
                    "depth": 0,
                    "author": str(comment.author) if comment.author else "[deleted]",
                    "replies": [],
                    "quality_score": min(comment.score / 1000, 1.0)
                }

                comment_chains.append(chain)
                processed += 1
                if processed >= max_comments:
                    break

            logging.debug(f"Processed {len(comment_chains)} comments for post {post.id}")
            return comment_chains

        except Exception as e:
            logging.error(f"Error processing comments for post {post.id}: {str(e)}")
            return []

    def calculate_engagement_score(self, post) -> float:
        """Calculate engagement score using configured weights"""
        score = (
                post.score * self.weights['upvote'] +
                post.num_comments * self.weights['comment'] +
                len(list(post.all_awardings)) * self.weights['award']
        )

        # Apply time decay if configured
        if self.weights.get('recency_decay'):
            hours_old = (datetime.utcnow().timestamp() - post.created_utc) / 3600
            decay_factor = max(0.1, 1 - (hours_old / self.weights['recency_decay']))
            score *= decay_factor

        return score

    def _get_random_sort_method(self):
        """Get a random sorting method with weighted probabilities"""
        methods = [
            ('hot', 0.35),  # Good for currently engaging content
            ('top', 0.30),  # Historically successful content
            ('rising', 0.20),  # Fresh content gaining traction
            ('new', 0.15)  # Completely fresh content
        ]
        return random.choices(
            population=[m[0] for m in methods],
            weights=[m[1] for m in methods]
        )[0]

    def _get_random_timeframe(self):
        """Get a random timeframe based on configured weights"""
        windows = self.time_windows
        window_names = [w['window'] for w in windows]
        window_weights = [w['weight'] for w in windows]

        return random.choices(
            population=window_names,
            weights=window_weights
        )[0]

    async def _process_time_window_async(self, subreddit, time_filter: str, target_count: int):
        """Process a single time window with enhanced variety"""
        logging.info(f"Processing time window: {time_filter}")
        posts = []

        try:
            # Get more posts than needed for better selection
            raw_posts = await self._get_posts_async(subreddit, time_filter, target_count * 2)

            for post in raw_posts:
                if len(posts) >= target_count:
                    break

                # Quick filtering based on settings
                if (self.post_settings['exclude_nsfw'] and post.over_18 or
                        len(post.title) > self.post_settings['max_title_length'] or
                        post.score < self.post_settings['min_score'] or
                        post.num_comments < self.post_settings['min_comments']):
                    continue

                # Add some randomness to engagement score for variety
                randomization_factor = random.uniform(0.8, 1.2)
                engagement_score = self.calculate_engagement_score(post) * randomization_factor

                comment_chains = await self._process_comments_async(
                    post,
                    max_comments=self.comment_settings['max_comments_per_post']
                )
                if not comment_chains:
                    continue

                post_data = {
                    "id": post.id,
                    "title": post.title,
                    "text": post.selftext if post.is_self else "",
                    "url": post.url,
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "created_utc": post.created_utc,
                    "engagement_score": engagement_score,
                    "subreddit": subreddit.display_name,
                    "is_self": post.is_self,
                    "permalink": f"https://reddit.com{post.permalink}",
                    "comment_chains": comment_chains
                }

                posts.append(post_data)
                logging.info(f"Collected post {len(posts)}/{target_count} from {time_filter}")

        except Exception as e:
            logging.error(f"Error in time window {time_filter}: {str(e)}")

        return posts

    def scrape_subreddit(self, subreddit_name: str, post_limit: int = None) -> List[Dict]:
        """Enhanced scraping with better content variety"""
        logging.info(f"Starting to scrape r/{subreddit_name}")

        if post_limit is None:
            post_limit = self.scraping_settings['default_post_limit']

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        subreddit = self.reddit.subreddit(subreddit_name)

        # Generate multiple diverse time windows
        time_windows = []
        remaining_posts = post_limit
        num_windows = random.randint(4, 6)  # More windows for better variety

        for _ in range(num_windows):
            if remaining_posts <= 0:
                break
            # Assign random portion of remaining posts to this window
            count = max(1, remaining_posts // (num_windows - len(time_windows)))
            time_windows.append((self._get_random_timeframe(), count))
            remaining_posts -= count

        # Process time windows concurrently
        async def process_all_windows():
            tasks = [
                self._process_time_window_async(subreddit, time_filter, count)
                for time_filter, count in time_windows
            ]
            results = await asyncio.gather(*tasks)
            all_posts = [post for window_posts in results for post in window_posts]

            # Remove any duplicates that might have slipped through
            seen_ids = set()
            unique_posts = []
            for post in all_posts:
                if post['id'] not in seen_ids:
                    seen_ids.add(post['id'])
                    unique_posts.append(post)

            # Sort by engagement score but with some randomness
            unique_posts.sort(
                key=lambda x: x["engagement_score"] * random.uniform(0.8, 1.2),
                reverse=True
            )

            return unique_posts[:post_limit]

        try:
            collected_posts = loop.run_until_complete(process_all_windows())
            logging.info(f"Successfully scraped {len(collected_posts)} posts from r/{subreddit_name}")
            return collected_posts

        except Exception as e:
            logging.error(f"Error scraping subreddit {subreddit_name}: {str(e)}")
            return []

    def create_directory_structure(self):
        """Create the necessary directory structure for content organization."""
        logging.info("Creating directory structure...")
        for path_name, path in self.paths.items():
            full_path = Path(path)
            logging.info(f"Creating directory: {full_path} (exists: {full_path.exists()})")
            full_path.mkdir(parents=True, exist_ok=True)

    def save_batch(self, posts: List[Dict], batch_id: str):
        """Save a batch of posts with all necessary metadata."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_name = f"{batch_id}_{timestamp}"

        # Save raw posts data
        raw_path = Path(self.paths['raw']) / f"{batch_name}.json"
        logging.info(f"Saving raw data to: {raw_path}")

        raw_path.parent.mkdir(parents=True, exist_ok=True)

        with open(raw_path, 'w', encoding='utf-8') as f:
            json.dump(posts, f, indent=2)

        # Create metadata
        metadata = {
            "batch_id": batch_name,
            "timestamp": timestamp,
            "num_posts": len(posts),
            "total_engagement": sum(p["engagement_score"] for p in posts),
            "posts_summary": [
                {
                    "id": p["id"],
                    "title": p["title"],
                    "engagement_score": p["engagement_score"]
                }
                for p in posts
            ]
        }

        metadata_path = Path(self.paths['metadata']) / f"{batch_name}.json"
        logging.info(f"Saving metadata to: {metadata_path}")

        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)

        logging.info(f"Saved batch {batch_name} with {len(posts)} posts")
        return batch_name