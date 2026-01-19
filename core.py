import re
from typing import List, Tuple


STOP = {
    "the","a","an","and","or","but","if","then","else","to","of","in","on","for","with","at","by","from","as",
    "is","are","was","were","be","been","being","it","this","that","these","those","i","you","we","they","he","she",
    "my","your","our","their","his","her","them","us","me","do","does","did","can","could","should","would","will",
    "about","into","over","under","up","down","out","very","more","most","less","least"
}


def _sentences(text: str) -> List[str]:
    # keep it robust for plain ASCII
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _words(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _keywords(text: str, k: int = 8) -> List[str]:
    w = [x for x in _words(text) if x not in STOP and len(x) >= 3]
    freq = {}
    for x in w:
        freq[x] = freq.get(x, 0) + 1
    ranked = sorted(freq.items(), key=lambda t: (-t[1], -len(t[0]), t[0]))
    return [x for x, _ in ranked[:k]]


def _score_sentence(s: str, keys: List[str]) -> int:
    sw = set(_words(s))
    return sum(2 for k in keys if k in sw) + min(len(sw) // 8, 3)


def _pick_top_sentences(text: str, n: int = 2) -> List[str]:
    sents = _sentences(text)
    if not sents:
        return []
    keys = _keywords(text, 10)
    scored = [(i, _score_sentence(s, keys), s) for i, s in enumerate(sents)]
    scored.sort(key=lambda t: (-t[1], t[0]))
    chosen = sorted(scored[: min(n, len(scored))], key=lambda t: t[0])
    return [s for _, _, s in chosen]


def _extract_topic(user_text: str) -> str:
    # try to detect "about X" / "of X" / "on X"
    m = re.search(r"\b(about|of|on)\b\s+(.+)$", user_text.strip(), re.IGNORECASE)
    if m:
        topic = m.group(2).strip()
        topic = re.sub(r"\s+", " ", topic)
        return topic[:120]
    # fallback to keywords
    keys = _keywords(user_text, 5)
    return " / ".join(keys) if keys else "the input"


def _intent(text: str) -> str:
    t = text.lower()
    # allow both "command-only" and "command+content"
    if "two sentence" in t or "2 sentence" in t:
        return "two_sentence"
    if "summarize" in t or "summary" in t:
        return "summarize"
    if ("bullet" in t) or ("bullet points" in t) or ("list" in t and "bullet" in t):
        return "bullets"
    if "explain" in t and ("child" in t or "simple" in t):
        return "explain_simple"
    if "explain" in t:
        return "explain"
    return "generic"


def think(text: str) -> str:
    it = _intent(text)

    # If the user only sends an instruction, we still produce content based on topic keywords.
    topic = _extract_topic(text)

    if it == "summarize":
        # Summarize the provided content: if the message is mostly an instruction, summarize keywords instead.
        tops = _pick_top_sentences(text, 2)
        if tops:
            summary = " ".join(tops)
            keys = _keywords(text, 6)
            key_line = f"Key points: {', '.join(keys)}." if keys else ""
            return (summary + (" " + key_line if key_line else "")).strip()
        keys = _keywords(text, 8)
        if not keys:
            return "Not enough content to summarize."
        return f"Summary: This is mainly about {', '.join(keys[:6])}."

    if it == "two_sentence":
        keys = _keywords(text, 6)
        kline = ", ".join(keys) if keys else topic
        return (
            f"This request is about {topic} and focuses on {kline}."
            f" A good response should be concise, specific, and directly address the intent."
        )

    if it == "bullets":
        keys = _keywords(text, 8)
        if not keys:
            keys = [topic]
        bullets = keys[:5]
        return "\n".join([f"- {b}" for b in bullets])

    if it == "explain_simple":
        keys = _keywords(text, 5)
        core = keys[0] if keys else topic
        return (
            f"Think of {core} like a simple tool that helps you do something easier."
            f" It takes an input, follows a few rules, and gives you an output you can use."
        )

    if it == "explain":
        keys = _keywords(text, 7)
        if not keys:
            return f"Explanation: {topic} means taking the input, understanding the goal, and producing the most useful output."
        return (
            f"Explanation: This relates to {topic}. "
            f"The key ideas here are: {', '.join(keys[:5])}. "
            f"In practice, you clarify the goal, pick the right method, then generate the result."
        )

    # generic
    keys = _keywords(text, 6)
    if keys:
        return (
            f"I interpreted the request as being about {topic}. "
            f"The most relevant concepts are: {', '.join(keys[:5])}. "
            f"Provide the missing specifics (constraints, examples, desired format) to get a sharper answer."
        )
    return "I received the input, but it lacks concrete details. Add constraints and an example to get a meaningful output."
