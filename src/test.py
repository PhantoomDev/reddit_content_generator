# Test script
from src.utils.config import ConfigManager
from src.scripts.generate_videos import generate_videos
import asyncio

async def test_video_generation():
    # Test with your existing batch
    batch_ids = ['batch_general_todayilearned_20241214_204906']
    result = await generate_videos('general', batch_ids)
    print(f"Generation result: {result}")

# Run the test
if __name__ == "__main__":
    asyncio.run(test_video_generation())