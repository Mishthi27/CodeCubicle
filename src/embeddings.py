from fastembed import TextEmbedding


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSION = 384

_model: TextEmbedding | None = None


def embed(text: str) -> list[float]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    global _model
    if _model is None:
        _model = TextEmbedding(model_name=MODEL_NAME)

    vector = next(_model.embed([text]))
    embedding = [float(value) for value in vector]
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"{MODEL_NAME} returned {len(embedding)} dimensions; "
            f"expected {EMBEDDING_DIMENSION}"
        )
    return embedding