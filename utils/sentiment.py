from transformers import pipeline

classifier = pipeline(
    "text-classification",
    model="w11wo/indonesian-roberta-base-sentiment-classifier",
    truncation=True
)

def predict_sentiment(
    title,
    content
):

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