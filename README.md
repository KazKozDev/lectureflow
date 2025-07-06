<div align="center">
<img src="https://github.com/user-attachments/assets/056fde13-5c55-41c8-8903-c4628b4ee1a4" alt="Timecode Logo" width="240">
</div>

# Timecoder

*YouTube Transcript Analyzer with AI-Powered Semantic Segmentation*

<div align="left">
  
  
  ![Python](https://img.shields.io/badge/python-v3.8+-blue.svg)
  ![License](https://img.shields.io/badge/license-MIT-green.svg)
  ![AI](https://img.shields.io/badge/AI-NLP%20%7C%20Transformers-orange.svg)
  ![GUI](https://img.shields.io/badge/GUI-Tkinter-red.svg)
  ![Status](https://img.shields.io/badge/status-demo-yellow.svg)
</div>

Timecoder is a Python application that analyzes YouTube video transcripts and organizes them into semantically related segments with timestamps. It's a demonstration project showcasing integration of modern NLP libraries for practical text analysis tasks.

### What makes it interesting?
- **Semantic Analysis**: Uses SentenceTransformer embeddings to group transcript segments by meaning rather than arbitrary time intervals
- **Multiple AI Models**: Combines different AI approaches - KeyBERT for keywords, DistilBART for summaries, and local Gemma3:12b for text improvement
- **Local Processing**: Runs entirely on your machine without sending data to external services
- **Real-world Application**: Solves the actual problem of navigating long YouTube videos

### Who is it for?
- **Students learning NLP**: Good example of combining multiple ML libraries
- **Developers** exploring AI integration in desktop applications
- **Content creators** who want to experiment with transcript analysis
- **Anyone curious** about semantic text processing

### Why does it exist?
This started as an experiment to see if AI could automatically create better structure for YouTube's often messy auto-generated transcripts. It's primarily a learning project that demonstrates practical applications of transformer models and semantic similarity.

## Tech Stack

**Core Technologies:**
- **Python 3.8+** - Main language
- **SentenceTransformer** - Text embeddings for semantic similarity
- **KeyBERT** - Keyword extraction
- **Transformers/DistilBART** - Text summarization
- **Ollama + Gemma3:12b** - Local LLM for text post-processing

**Supporting Libraries:**
- **NLTK** - Text preprocessing
- **YouTube Transcript API** - Getting video transcripts
- **Tkinter + ttkbootstrap** - Desktop GUI
- **tkinterweb** - HTML rendering in GUI
- **Requests** - HTTP communication

## Demo

![Timecoder Screenshot](https://github.com/user-attachments/assets/e41ee732-2dd7-4cee-8153-7b43bcb52c2b)

## Installation & Setup

### Prerequisites
- Python 3.8+
- ~11GB disk space for the Gemma3:12b model
- Internet connection for initial setup

### Installation Steps

1. **Clone and setup**
   ```bash
   git clone https://github.com/KazKozDev/timecoder.git
   cd timecoder
   python -m venv venv
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. **Install Ollama and model**
   ```bash
   # Install Ollama (see https://ollama.com for platform-specific instructions)
   ollama serve
   ollama pull gemma3:12b
   ```

3. **Setup NLTK data**
   ```python
   python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
   ```

4. **Update Hugging Face token**
   Edit line 27 in `timecoder.py` and replace with your token (or remove the login line)

### Quick Start
```bash
python timecoder.py
```

## Usage

1. Launch the application
2. Paste a YouTube URL (must have available transcripts)
3. Click "Analyze Transcript" and wait
4. View the timestamped segments in the output
5. Use "Copy All" to get the formatted text

**Note**: Processing can take several minutes depending on video length and your hardware.

## How It Works

### Processing Pipeline
1. **Extract transcript** from YouTube using their API
2. **Clean and preprocess** text (remove filler words, normalize)
3. **Create chunks** of transcript segments for analysis
4. **Generate embeddings** using SentenceTransformer
5. **Group by similarity** using cosine similarity thresholds
6. **Extract topics** with KeyBERT or DistilBART
7. **Post-process** with Gemma3:12b for better formatting
8. **Display** results in GUI with timestamps

### Key Implementation Details
- Uses dynamic similarity thresholds to balance segment granularity
- Falls back to forced segmentation if semantic grouping produces too few segments
- Includes comprehensive error handling for flaky AI model responses
- Processes everything locally for privacy

## Limitations & Known Issues

- **Processing Time**: Can be slow on older hardware (several minutes per hour of video)
- **Memory Usage**: Requires significant RAM during processing (~2-4GB)
- **Model Dependencies**: Relies on external models that may not always be available
- **No Persistence**: Results aren't saved automatically
- **Limited Error Recovery**: May fail on videos with unusual transcript formats
- **No Testing**: This is a demo project without formal test coverage

## Project Structure

```
timecoder/
├── timecoder.py          # Main application
├── requirements.txt      # Python dependencies
├── README.md            # This file
├── LICENSE              # MIT license
└── .gitignore          # Git ignore rules
```

## Contributing

Feel free to fork and experiment! This is a learning project, so I welcome:
- Bug fixes
- Performance improvements
- UI enhancements
- Better error handling

No formal contribution guidelines - just open an issue or PR.

---

If you like this project, please give it a star ⭐

For questions, feedback, or support, reach out to:

[Artem KK](https://www.linkedin.com/in/kazkozdev/) | MIT [LICENSE](LICENSE)


**Disclaimer**: This is a learning/demo project, not production software. Use at your own risk.

<div align="center">

*A practical exploration of NLP and semantic analysis*

</div>
