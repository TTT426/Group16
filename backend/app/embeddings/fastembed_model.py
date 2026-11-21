"""Small ONNX embedding model via fastembed (no torch). Install with `pip install -e ".[embeddings]"`.

Default model: BAAI/bge-small-zh-v1.5 (~90 MB, 512-d, Chinese + English). On our two evaluation
scenarios it retrieved the answer sources better than the 2 GB bge-m3 (see docs/PROJECT_PLAN.md §9).
The model is downloaded on first use into `data/models/` inside the repo.
"""

import math

from ..config import REPO_ROOT

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
CACHE_DIR = REPO_ROOT / "data" / "models"


def _normalise(vector) -> list[float]:
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


class FastEmbedEmbedder:
    name = "fastembed"

    def __init__(self, model_name: str = "", batch_size: int = 32) -> None:
        self.model_name = model_name or DEFAULT_MODEL
        self.model_id = f"fastembed:{self.model_name}"
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(self.model_name, cache_dir=str(CACHE_DIR))
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [_normalise(v) for v in self.model.embed(texts, batch_size=self.batch_size)]

    def embed_query(self, text: str) -> list[float]:
        return _normalise(next(iter(self.model.query_embed(text))))
