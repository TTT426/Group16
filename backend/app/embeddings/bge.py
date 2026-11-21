"""Local sentence-transformers embedder (default model: BAAI/bge-m3, multilingual, 1024-d).

Install with `pip install -e ".[embeddings]"`. The model (~2 GB) is downloaded on first use.
"""


class SentenceTransformerEmbedder:
    name = "bge"

    def __init__(self, model_name: str = "BAAI/bge-m3", dim: int = 1024, batch_size: int = 16) -> None:
        self.model_name = model_name
        self.dim = dim
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError('sentence-transformers is not installed: pip install -e ".[embeddings]"') from exc
            self._model = SentenceTransformer(self.model_name)
            get_dim = getattr(self._model, "get_embedding_dimension", None) or (
                self._model.get_sentence_embedding_dimension  # sentence-transformers < 5
            )
            actual = get_dim()
            if actual != self.dim:
                raise RuntimeError(f"{self.model_name} produces {actual}-d vectors but EMBEDDING_DIM={self.dim}.")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
