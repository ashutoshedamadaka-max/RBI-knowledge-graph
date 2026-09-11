import hashlib
import math
import re


class HashingEmbedder:
    """Dependency-free local baseline embedding.

    Feature hashing keeps vectors deterministic across processes and makes the
    Phase 2 retrieval baseline runnable without downloading a model. It is a
    lexical baseline, not a substitute for a sentence-transformer model.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[a-z0-9]{2,}", text.lower())
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            position = int.from_bytes(digest, "big") % self.dimensions
            vector[position] += 1.0
        magnitude = math.sqrt(sum(value * value for value in vector))
        return [value / magnitude for value in vector] if magnitude else vector

    @staticmethod
    def similarity(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right))

