"""Agentic search and Q&A over video library."""

from pathlib import Path

import yaml

from src.db.repository import AnalysisRepository
from src.llm.base import BaseLLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _load_agent_prompt(config_path: str | None = None) -> str:
    if config_path is None:
        config_path = str(
            Path(__file__).parent.parent.parent / "config" / "prompts.yaml"
        )
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
            return config.get("templates", {}).get(
                "agent_qa", "Answer based on context: {context}\nQuestion: {question}"
            )
    except (FileNotFoundError, KeyError, yaml.YAMLError):
        return "Answer based on context:\n{context}\n\nQuestion: {question}"


class VideoAgent:
    """Agent for semantic Q&A over the video database."""

    def __init__(self, db: AnalysisRepository, llm_client: BaseLLMClient):
        self.db = db
        self.llm_client = llm_client

    def chat(
        self,
        query: str,
        limit: int = 20,
        provider: str | None = None,
        model_name: str | None = None,
        language: str | None = None,
    ) -> str:
        """Answer a user query based on the video segments database.

        Args:
            query: The user's question.
            limit: Max segments to retrieve as context.
            provider: LLM provider override
            model_name: LLM model override

        Returns:
            The agent's synthesized response.
        """
        # 1. Retrieve segments using hybrid search over titles/topics/text
        results = self.db.search_segments(query, limit)
        if not results:
            return "No relevant video segments found to answer your question."

        # 2. Format context
        context_parts = []
        for r in results:
            start_m = int(r["start_time"] // 60)
            start_s = int(r["start_time"] % 60)
            context_parts.append(
                f"Video ID: {r['video_id']}\n"
                f"Video Title: {r.get('title') or r['video_id']}\n"
                f"Time: [{start_m:02d}:{start_s:02d}]\n"
                f"Topic: {r['topic']}\n"
                f"Text: {r['text']}\n"
            )

        context_str = "\n".join(context_parts)

        # 3. Prompt LLM
        template = _load_agent_prompt()
        prompt = template.format(context=context_str, question=query)

        if language and language.lower() not in ["auto", ""]:
            prompt += f"\n\nCRITICAL INSTRUCTION: You MUST write your ultimate answer entirely in {language}."

        client = self.llm_client
        if provider or model_name:
            from src.llm.factory import create_llm_client

            overrides = {}
            if model_name:
                overrides["model_name"] = model_name
            try:
                client = create_llm_client(provider=provider, **overrides)
            except Exception as e:
                logger.warning(
                    "Failed to create custom agent LLM client, using default. %s", e
                )

        logger.info(
            "Agent processing query: '%s' with %d segments using %s",
            query,
            len(results),
            client.get_provider_name(),
        )
        response = client.complete(prompt)
        return response
