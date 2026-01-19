import re
from typing import List

def _split_sentences(text: str) -> List[str]:
    return [s.strip() for s in re.split(r"[.!?]", text) if s.strip()]

def think(text: str) -> str:
    t = text.lower().strip()

    if "two sentence" in t or "2 sentence" in t:
        return (
            "This request asks for a short, concise response. "
            "Here is a second sentence that completes the thought clearly."
        )

    if "summarize" in t or "summary" in t:
        sentences = _split_sentences(text)
        if not sentences:
            return "There is not enough information to summarize."
        if len(sentences) == 1:
            return sentences[0]
        return sentences[0] + ". " + sentences[-1] + "."

    if "explain" in t and "child" in t:
        return (
            "Imagine this idea like a simple story. "
            "It means doing something in an easy and understandable way."
        )

    if "bullet" in t or "list" in t:
        return (
            "- First key idea\n"
            "- Second important point\n"
            "- Supporting detail\n"
            "- Practical implication\n"
            "- Final takeaway"
        )

    return (
        "I read the input and identified its intent. "
        "Then I selected an appropriate response strategy and produced this output."
    )
