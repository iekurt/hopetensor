# ============================================================
# HOPETENSOR — Reasoning Infrastructure
#
# Author        : Erhan Kurt (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# This file is part of the Hopetensor core reasoning system.
# Designed to serve humanity with conscience-aware AI.
#
# "Yurtta barış, Cihanda barış"
# "In GOD we HOPE"
# ============================================================


import hashlib
import re
from typing import List


STOP = {
    "the","a","an","and","or","but","if","then","else","to","of","in","on","for","with","at","by","from","as",
    "is","are","was","were","be","been","being","it","this","that","these","those","i","you","we","they","he","she",
    "my","your","our","their","his","her","them","us","me","do","does","did","can","could","should","would","will",
    "about","into","over","under","up","down","out","very","more","most","less","least","please","make","create",
    "write","generate","give","provide","response","output","sentences","sentence"
}


def _seed(text: str) -> int:
    h = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
    return int(h[:8], 16)


def _pick(text: str, options: List[str]) -> str:
    if not options:
        return ""
    s = _seed(text)
    return options[s % len(options)]


def _words(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _keywords(text: str, k: int = 10) -> List[str]:
    w = [x for x in _words(text) if x not in STOP and len(x) >= 3]
    freq = {}
    for x in w:
        freq[x] = freq.get(x, 0) + 1
    ranked = sorted(freq.items(), key=lambda t: (-t[1], -len(t[0]), t[0]))
    return [x for x, _ in ranked[:k]]


def _extract_payload(text: str) -> str:
    """
    Supports:
      summarize: <payload>
      bullets: <payload>
      explain: <payload>
      2sent: <payload>
    If no payload found, payload = full text.
    """
    m = re.match(r"^\s*(summarize|summary|bullets|bullet|list|explain|2sent|two)\s*:\s*(.+)\s*$", text, re.I)
    if m:
        return m.group(2).strip()
    return text.strip()


def _intent(text: str) -> str:
    t = text.lower().strip()
    if re.match(r"^\s*(summarize|summary)\s*:", t):
        return "summarize"
    if re.match(r"^\s*(bullets|bullet|list)\s*:", t):
        return "bullets"
    if re.match(r"^\s*(explain)\s*:", t):
        return "explain"
    if re.match(r"^\s*(2sent|two)\s*:", t):
        return "two_sentence"

    # fallback heuristics
    if "summarize" in t or "summary" in t:
        return "summarize"
    if "bullet" in t or ("list" in t and "point" in t):
        return "bullets"
    if "two sentence" in t or "2 sentence" in t:
        return "two_sentence"
    if "explain" in t:
        return "explain"
    return "generic"


def _top_sentences(payload: str, n: int = 2) -> List[str]:
    sents = _sentences(payload)
    if not sents:
        return []
    keys = _keywords(payload, 12)
    scored = []
    for i, s in enumerate(sents):
        sw = set(_words(s))
        score = sum(2 for k in keys if k in sw) + min(len(sw) // 8, 3)
        scored.append((score, i, s))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen = sorted(scored[: min(n, len(scored))], key=lambda x: x[1])
    return [s for _, _, s in chosen]


def think(text: str) -> str:
    it = _intent(text)
    payload = _extract_payload(text)

    keys = _keywords(payload, 10)
    topic = ", ".join(keys[:4]) if keys else "the input"

    if it == "summarize":
        tops = _top_sentences(payload, 2)
        if tops:
            opener = _pick(payload, [
                "Summary:",
                "In short:",
                "Quick summary:",
                "Key takeaway:"
            ])
            kline = ""
            if keys:
                kline = " Key terms: " + ", ".join(keys[:6]) + "."
            return f"{opener} " + " ".join(tops) + kline
        return "Summary: Not enough content to summarize."

    if it == "bullets":
        bullets = keys[:6] if keys else _keywords(text, 6)
        if not bullets:
            bullets = ["point 1", "point 2", "point 3"]
        prefix = _pick(payload, ["- ", "• ", "* "])
        return "\n".join([prefix + b for b in bullets])

    if it == "explain":
        style = _pick(payload, ["plain", "practical", "structured"])
        if style == "plain":
            return (
                f"This is mainly about {topic}. "
                f"It means taking the core idea, removing noise, and explaining it clearly with examples."
            )
        if style == "practical":
            return (
                f"Practical explanation for {topic}: "
                f"identify the goal, list constraints, choose a method, and produce a usable result."
            )
        return (
            f"Explanation ({topic}): "
            f"(1) Goal, (2) Inputs, (3) Method, (4) Output, (5) Checks/risks."
        )

    if it == "two_sentence":
        a = _pick(payload, [
            f"This request centers on {topic} and needs a concise answer.",
            f"The main theme here is {topic}, and the output should be short and clear.",
            f"You are asking about {topic}; a tight response is best."
        ])
        b = _pick(payload, [
            "To improve quality, add constraints, examples, and the exact desired format.",
            "If you provide context and constraints, the answer becomes dramatically sharper.",
            "Give a bit more context and I can produce a more specific, actionable response."
        ])
        return a + " " + b

    # generic: make output depend on payload strongly
    frame = _pick(payload, [
        f"I detect the topic as {topic}.",
        f"This looks like a request about {topic}.",
        f"The key concepts I see are {topic}."
    ])
    action = _pick(payload, [
        "Tell me the target audience and constraints to optimize the output.",
        "Add one example input/output pair and I will match that style.",
        "Specify length, tone, and format (bullets, JSON, paragraph) for best results."
    ])
    return frame + " " + action
