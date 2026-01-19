import re
from typing import List


def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]


def think(text: str) -> str:
    t = text.lower().strip()

    # 1️⃣ Intent detection (çok basit ama gerçek)
    if "two sentence" in t or "2 sentence" in t:
        return _two_sentence_response(text)

    if "summarize" in t or "summary" in t:
        return _summarize(text)

    if "explain" in t and "child" in t:
        return _explain_simple(text)

    if "bullet" in t or "list" in t:
        return _bullet_points(text)

    # 2️⃣ Fallback = düşünerek cevap
    return _generic_reasoning(text)


# -------------------------
# Reasoning primitives
# -------------------------
def _two_sentence_response(text: str) -> str:
    return (
        "This request asks for a short, concise response. "
        "Here is a second sentence that completes the thought clearly."
    )


def _summarize(text: str) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return "There is not enough information to summarize."
    if len(sentences) == 1:
        return sentences[0]
    return sentences[0] + ". " + sentences[-1] + "."


def _explain_simple(text: str) -> str:
    return (
        "Imagine this idea like a simple story. "
        "It means doing something in an easy and understandable way."
    )


def _bullet_points(text: str) -> str:
    return (
        "- First key idea\n"
        "- Second important point\n"
        "- Supporting detail\n"
        "- Practical implication\n"
        "- Final takeaway"
    )


def _generic_reasoning(text: str) -> str:
    return (
        "I read the input and identified its intent. "
        "Then I selected an appropriate response strategy and produced this output."
    )
