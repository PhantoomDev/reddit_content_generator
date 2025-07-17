# Automated Content Generation Pipeline

A high-performance Python application for automated content aggregation and video generation, featuring parallel processing and multi-stage pipeline architecture.

## 🚀 Technical Highlights

- **Parallel Processing**: Utilizes multiprocessing for concurrent TTS generation and video rendering
- **Modular Architecture**: Clean separation of concerns with dedicated modules for scraping, processing, and generation
- **API Integration**: Robust Reddit API integration with rate limiting and error handling
- **Automated Pipeline**: End-to-end automation from content aggregation to final video output
- **Batch Processing**: Efficient handling of large content batches with metadata tracking

## 📋 Features

- **Content Aggregation**: Automated Reddit content scraping with configurable subreddit targeting
- **Content Filtering**: Multi-stage filtering pipeline for quality control
- **Text-to-Speech**: Batch TTS generation with segment management
- **Video Generation**: Automated video composition with multiple tracks (content, background, audio)
- **Configuration Management**: YAML-based configuration for easy customization

## 🏗️ Architecture

```
reddit_content_generator/
├── src/
│   ├── scrapers/          # Reddit API integration
│   ├── processors/        # Content filtering and TTS preparation
│   ├── generators/        # Video and audio generation
│   ├── scripts/           # Pipeline orchestration scripts
│   └── utils/             # Configuration and utilities
├── content/               # Generated content storage
└── config/                # Configuration files
```

## 🛠️ Technology Stack

- **Language**: Python 3.8+
- **APIs**: Reddit API (PRAW)
- **Video Processing**: FFmpeg
- **Audio Processing**: Microsoft Speech SDK / Text-to-Speech APIs
- **Parallel Processing**: Python multiprocessing
- **Configuration**: YAML

## 📦 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/content-generation-pipeline.git
cd content-generation-pipeline
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install Microsoft Speech SDK (if using Azure TTS):
```bash
# Download from: https://aka.ms/csspeech/pythonref
# Follow platform-specific installation instructions
```

4. Configure settings:
```bash
cp config/settings.example.yaml config/settings.yaml
# Edit config/settings.yaml with your API credentials
```

4. Set up required directories:
```bash
# Create directory structure
mkdir -p content/{audio,videos,raw,filtered,processed,metadata,images}
mkdir -p content/stock_footage/{gaming/{vertical,horizontal},satisfying/{vertical,horizontal},fixed}
mkdir -p content/music
```

5. Add your assets:
   - Stock footage in `content/stock_footage/` (see README in that directory)
   - Background music in `content/music/` (see README in that directory)

## 🚦 Usage

### Full Pipeline Execution:
```bash
python src/main.py
```

### Individual Components:
```bash
# Scrape content
python src/scripts/scrape.py

# Filter content
python src/scripts/filter.py

# Generate TTS
python src/scripts/generate_tts.py

# Generate videos
python src/scripts/generate_videos.py
```

## 🔧 Configuration

The pipeline is highly configurable through `config/settings.yaml`:

### Key Configuration Areas:

- **Scraping Settings**:
  - Subreddit categorization (general, tech, pop)
  - Post/comment filtering criteria
  - Engagement scoring weights
  - Rate limiting controls

- **Content Filtering**:
  - Quality thresholds
  - Excluded phrases/topics
  - Segment limits

- **TTS Processing**:
  - Multiple voice personas
  - Speed and formatting controls
  - Parallel worker configuration

- **Video Generation**:
  - Separate settings for shorts/longform
  - Stock footage categorization
  - Export quality settings

See `config/settings.example.yaml` for full configuration options.

## 📊 Performance

- Parallel processing reduces generation time by up to 75%
- Capable of processing 100+ pieces of content daily
- Automatic batch management for optimal resource utilization

## 🤝 Contributing

This project was originally developed for personal use but is now open-sourced for educational purposes. Contributions are welcome!

## 📄 License

MIT License - See LICENSE file for details

## 🎯 Future Enhancements

- [ ] Add support for additional content sources
- [ ] Implement ML-based content quality scoring
- [ ] Add real-time processing capabilities
- [ ] Expand video template options

---

**Note**: This project is intended for educational and research purposes. Please ensure compliance with all relevant APIs' terms of service and content usage policies.