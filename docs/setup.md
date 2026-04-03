# Setup Guide

## Prerequisites

- Python 3.11 or higher
- At least one LLM API key (OpenAI, Anthropic, Groq, or Grok) — or a local Ollama installation
- Git

## Local Installation

```bash
git clone https://github.com/KazKozDev/lectureflow.git
cd lectureflow

python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

## Environment Variables

Copy the example file and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | No* | OpenAI API key |
| `ANTHROPIC_API_KEY` | No* | Anthropic API key |
| `GROQ_API_KEY` | No* | Groq API key |
| `XAI_API_KEY` | No* | Grok (xAI) API key |
| `LLM_PROVIDER` | No | Default provider: `openai`, `anthropic`, `groq`, `grok`, `ollama` (default: `openai`) |
| `OLLAMA_BASE_URL` | No | Ollama server URL (default: `http://localhost:11434`) |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |

*At least one LLM provider key is required unless using Ollama.

## Running

```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser. The web UI is served automatically.

## Docker

```bash
cp .env.example .env
# Edit .env with your API keys

# Standard (cloud LLM providers only)
docker compose up

# With local Ollama for offline inference
docker compose --profile local up
```

The app is available at `http://localhost:8000`. Ollama (if enabled) runs on port `11434`.

Data is persisted in a Docker volume (`timecoder-data`).

## Troubleshooting

**PyTorch MPS warnings on Apple Silicon:** The app automatically sets `PYTORCH_ENABLE_MPS_FALLBACK=1` and runs embeddings on CPU. No action needed.

**NLTK data missing:** If you see NLTK errors, download the required data:

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('punkt_tab'); nltk.download('stopwords')"
```

**Ollama connection refused:** Ensure Ollama is running (`ollama serve`) and the `OLLAMA_BASE_URL` in `.env` matches your setup.
