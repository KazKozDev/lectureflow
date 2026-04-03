# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - Unreleased

### Added

- FastAPI REST API with streaming analysis (NDJSON)
- Multi-provider LLM support (OpenAI, Anthropic, Groq, Grok, Ollama)
- Semantic segmentation using sentence-transformer embeddings
- Topic annotation with KeyBERT
- 6 analysis modes: detailed, brief, exam, flashcards, quiz, youtube_seo
- SQLite persistence with FTS5 full-text search
- RAG-based Q&A agent over video library
- Playlist batch processing
- Export to JSON, Markdown, SRT, YouTube description
- Web UI with provider selection and library browser
- Docker + Docker Compose deployment
- Whisper audio fallback for transcript extraction
- Semantic and YouTube-based video recommendations
