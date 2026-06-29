import os


MODEL_NAME = "w11wo/indonesian-roberta-base-sentiment-classifier"
_classifier = None


def load_classifier():
    global _classifier

    if _classifier is not None:
        return _classifier

    if os.getenv("SENTIMENT_MODE", "").lower() in {"neutral", "skip", "fast"}:
        print(
            "Sentiment mode is neutral/fast; HuggingFace model is skipped.",
            flush=True,
        )
        return None

    print("Sentiment: importing transformers.pipeline...", flush=True)
    from transformers import pipeline

    print(f"Sentiment: loading model {MODEL_NAME}...", flush=True)
    _classifier = pipeline(
        "text-classification",
        model=MODEL_NAME,
        truncation=True,
    )
    print("Sentiment: model ready.", flush=True)

    return _classifier

def predict_sentiment(
    title,
    content
):
    classifier = load_classifier()

    if classifier is None:
        return (
            "neutral",
            0.0,
        )

    text = (
        str(title)
        + " "
        + str(content)
    )[:512]

    result = classifier(text)[0]

    return (
        result["label"],
        result["score"]
    )
