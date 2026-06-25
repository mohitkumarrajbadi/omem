"""Online tuning of retrieval weights from agent feedback."""

from dataclasses import replace

from ..retrieval.fusion import FusionWeights


def tune_weights_from_feedback(
    weights: FusionWeights,
    feedback_score: float,
    learning_rate: float = 0.05,
) -> FusionWeights:
    """Nudge fusion weights based on positive/negative retrieval feedback.

    Positive feedback slightly boosts semantic + graph weights.
    Negative feedback slightly boosts recency + importance weights.
    """
    score = max(min(feedback_score, 1.0), -1.0)
    lr = learning_rate

    if score >= 0:
        return FusionWeights(
            semantic=min(weights.semantic + lr * score, 0.45),
            keyword=weights.keyword,
            recency=max(weights.recency - lr * score * 0.5, 0.05),
            importance=weights.importance,
            confidence=min(weights.confidence + lr * score * 0.5, 0.15),
            graph=min(weights.graph + lr * score, 0.20),
            personalization=weights.personalization,
        )

    magnitude = abs(score)
    return FusionWeights(
        semantic=max(weights.semantic - lr * magnitude * 0.5, 0.15),
        keyword=weights.keyword,
        recency=min(weights.recency + lr * magnitude, 0.25),
        importance=min(weights.importance + lr * magnitude, 0.30),
        confidence=weights.confidence,
        graph=max(weights.graph - lr * magnitude * 0.5, 0.03),
        personalization=weights.personalization,
    )


def normalize_weights(weights: FusionWeights) -> FusionWeights:
    """Renormalize weights to sum to 1.0."""
    total = sum(weights.as_dict().values())
    if total <= 0:
        return FusionWeights()
    factor = 1.0 / total
    return replace(
        weights,
        semantic=weights.semantic * factor,
        keyword=weights.keyword * factor,
        recency=weights.recency * factor,
        importance=weights.importance * factor,
        confidence=weights.confidence * factor,
        graph=weights.graph * factor,
        personalization=weights.personalization * factor,
    )
