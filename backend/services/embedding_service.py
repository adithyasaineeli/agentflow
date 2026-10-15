import hashlib
import logging
import math
import os
import random
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger("agentflow.embedding")


class BaseEmbeddingService(ABC):
    """Abstract interface for generating vector embeddings."""

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """Generate a 1536-dimensional embedding vector for the given text."""
        pass


class OpenAIEmbeddingService(BaseEmbeddingService):
    """Generates 1536-dimensional embeddings using OpenAI's text-embedding-3-small model."""

    def __init__(self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY must be set to use OpenAIEmbeddingService.")
        self.model = model

        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("The 'openai' package is required. Run `pip install openai`.")

    def generate_embedding(self, text: str) -> List[float]:
        clean_text = text.replace("\n", " ").strip()
        if not clean_text:
            clean_text = "empty"

        response = self.client.embeddings.create(
            input=[clean_text],
            model=self.model,
        )
        return response.data[0].embedding


class MockEmbeddingService(BaseEmbeddingService):
    """Deterministic token-hashing 1536-dimensional vector generator.

    Provides semantic keyword and subword overlap matching when OPENAI_API_KEY
    is not configured or during offline testing.
    """

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def generate_embedding(self, text: str) -> List[float]:
        import re

        vector = [0.0] * self.dimension
        clean = text.lower()
        words = re.findall(r"[a-z0-9_]+", clean)
        if not words:
            words = ["empty"]

        # Collect unigrams, bigrams, and character 3-grams
        tokens = list(words)
        for i in range(len(words) - 1):
            tokens.append(f"{words[i]}_{words[i+1]}")
        for word in words:
            if len(word) >= 3:
                for j in range(len(word) - 2):
                    tokens.append(word[j : j + 3])

        for token in tokens:
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dimension
            sign = 1.0 if (h >> 16) & 1 else -1.0
            vector[idx] += sign

        # Unit normalize (L2 norm = 1.0)
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [round(x / norm, 6) for x in vector]


def get_embedding_service() -> BaseEmbeddingService:
    """Factory creating OpenAIEmbeddingService if configured, otherwise MockEmbeddingService."""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            service = OpenAIEmbeddingService(api_key=api_key)
            logger.info("Initialized OpenAIEmbeddingService (model: text-embedding-3-small).")
            return service
        except Exception as exc:
            logger.warning(
                f"Failed to initialize OpenAIEmbeddingService ({exc}). Falling back to MockEmbeddingService."
            )

    logger.info("OPENAI_API_KEY not found or inactive. Falling back to deterministic MockEmbeddingService.")
    return MockEmbeddingService()
