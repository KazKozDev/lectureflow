"""Semantic segmentation of transcript chunks."""

from pathlib import Path

import torch
import yaml
from sentence_transformers import SentenceTransformer, util

from src.utils.logger import get_logger

logger = get_logger(__name__)


class SemanticSegmenter:
    """Groups transcript chunks by semantic similarity.

    Args:
        model_name: SentenceTransformer model to use for embeddings.
        config_path: Path to model_config.yaml for segmentation params.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        config_path: str | None = None,
    ) -> None:
        # Keep semantic embeddings on CPU: sparse ops used by sentence-transformers/KeyBERT
        # are still unstable on MPS for this pipeline.
        self.model = SentenceTransformer(model_name, device="cpu")
        self._load_config(config_path)

    def _load_config(self, config_path: str | None) -> None:
        """Load segmentation parameters from config."""
        defaults = {
            "chunk_size": 8,
            "similarity_threshold": 0.35,
            "min_chunks_per_group": 2,
            "max_chunks_per_group": 8,
            "forced_groups_count": 5,
        }

        if config_path is None:
            config_path = str(
                Path(__file__).parent.parent.parent / "config" / "model_config.yaml"
            )

        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
                seg_config = config.get("segmentation", {})
                defaults.update(seg_config)
        except (FileNotFoundError, yaml.YAMLError):
            logger.debug("Using default segmentation config")

        self.chunk_size: int = defaults["chunk_size"]
        self.similarity_threshold: float = defaults["similarity_threshold"]
        self.min_chunks: int = defaults["min_chunks_per_group"]
        self.max_chunks: int = defaults["max_chunks_per_group"]
        self.forced_groups_count: int = defaults["forced_groups_count"]

    def create_chunks(self, segments: list[tuple[str, float, float]]) -> list[str]:
        """Create text chunks from segments for semantic analysis.

        Args:
            segments: List of (text, start, duration) tuples.

        Returns:
            List of concatenated text chunks.
        """
        chunks = []
        for i in range(0, len(segments), self.chunk_size):
            chunk_text = " ".join([s[0] for s in segments[i : i + self.chunk_size]])
            chunks.append(chunk_text)
        logger.info("Created %d chunks for analysis", len(chunks))
        return chunks

    def group_by_similarity(self, chunks: list[str]) -> list[list[int]]:
        """Group chunk indices by semantic similarity.

        Args:
            chunks: List of text chunks.

        Returns:
            List of groups, where each group is a list of chunk indices.
        """
        if not chunks:
            return []

        embeddings = self.model.encode(chunks, convert_to_tensor=True)

        groups: list[list[int]] = []
        current_group = [0]

        for i in range(1, len(chunks)):
            group_embedding = torch.mean(embeddings[current_group], dim=0)
            similarity = util.cos_sim(group_embedding, embeddings[i]).item()

            if (
                similarity >= self.similarity_threshold
                and len(current_group) < self.max_chunks
            ) or len(current_group) < self.min_chunks:
                current_group.append(i)
            else:
                groups.append(current_group)
                current_group = [i]

        if current_group:
            groups.append(current_group)

        logger.info("Created %d semantic groups", len(groups))
        return groups

    def resolve_groups(
        self,
        segments: list[tuple[str, float, float]],
        chunk_groups: list[list[int]],
    ) -> list[dict]:
        """Convert chunk groups back to segment-level groups with timestamps.

        Args:
            segments: Original segments (text, start, duration).
            chunk_groups: Groups of chunk indices.

        Returns:
            List of dicts with start_time, end_time, text, segment_count.
        """
        results = []

        for group_indices in chunk_groups:
            seg_indices: list[int] = []
            for chunk_idx in group_indices:
                start_idx = chunk_idx * self.chunk_size
                end_idx = min(start_idx + self.chunk_size, len(segments))
                seg_indices.extend(range(start_idx, end_idx))

            seg_indices = sorted(set(seg_indices))

            if seg_indices:
                start_time = segments[seg_indices[0]][1]
                last = segments[seg_indices[-1]]
                end_time = last[1] + last[2]
                text = " ".join(segments[idx][0] for idx in seg_indices)

                results.append(
                    {
                        "start_time": start_time,
                        "end_time": end_time,
                        "text": text,
                        "segment_count": len(seg_indices),
                    }
                )

        return results

    def segment(self, segments: list[tuple[str, float, float]]) -> list[dict]:
        """Full segmentation pipeline.

        Args:
            segments: Raw transcript segments.

        Returns:
            Semantically grouped segments with timestamps.
        """
        chunks = self.create_chunks(segments)
        groups = self.group_by_similarity(chunks)
        results = self.resolve_groups(segments, groups)

        # Fallback to forced segmentation if too few groups
        if len(results) <= 1 and len(segments) > self.forced_groups_count:
            logger.info("Too few groups, using forced segmentation")
            results = self._forced_segmentation(segments)

        return results

    def _forced_segmentation(
        self, segments: list[tuple[str, float, float]]
    ) -> list[dict]:
        """Force equal-sized groups when semantic grouping fails.

        Args:
            segments: Raw transcript segments.

        Returns:
            Evenly divided segment groups.
        """
        n = self.forced_groups_count
        per_group = len(segments) // n
        results = []

        for i in range(n):
            start_idx = i * per_group
            end_idx = start_idx + per_group if i < n - 1 else len(segments)
            start_time = segments[start_idx][1]
            last = segments[end_idx - 1]
            end_time = last[1] + last[2]
            text = " ".join(segments[idx][0] for idx in range(start_idx, end_idx))

            results.append(
                {
                    "start_time": start_time,
                    "end_time": end_time,
                    "text": text,
                    "segment_count": end_idx - start_idx,
                }
            )

        return results
