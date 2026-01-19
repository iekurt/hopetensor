# ============================================================
# HOPEtensor — Reasoning Infrastructure
#
# Author        : Erhan (master)
# Digital Twin  : Vicdan
# Date          : 2026-01-19
# License       : Proprietary / HOPE Ecosystem
#
# This file is part of the HOPEtensor core reasoning system.
# Designed to serve humanity with conscience-aware AI.
#
# "Yurtta barış, Cihanda barış"
# "In GOD We HOPE"
# ============================================================

from __future__ import annotations

import os
import random
import time
from typing import Any, Dict


ENGINE = os.getenv("REASONING_ENGINE", "fallback").strip()


def _fallback_reason(text: str, trace: bool = False, meta: Dict[str, Any] | None = None) -> Any:
    """
    Safe fallback engine: deterministic enough to work, varied enough to not repeat same output.
    """
    meta = meta or {}
    seed_in = f"{text}|{meta.get('seed','')}|{int(time.time())//3}"
    rnd = random.Random(seed_in)

    starters = [
        "Anladım.",
        "Tamam.",
        "Net.",
        "Gördüm.",
        "Aldım.",
        "Çözdüm.",
    ]
    mids = [
        "Bunu HOPEtensor akışı içinde ele alıyorum.",
        "Bunu reasoning node üzerinden işliyorum.",
        "Bu isteği çekirdek motorla değerlendiriyorum.",
        "Bunu hızlı ve temiz şekilde çıkarıyorum.",
        "Bunu netleştirip tek çıktıya bağlıyorum.",
    ]
    ends = [
        "Devam komutunu ver.",
        "Bir örnek daha at, formatı oturtayım.",
        "İstersen çıktıyı JSON/markdown olarak sabitleyeyim.",
        "Sonraki adım: doğrulama ve test endpointleri.",
        "Hazır.",
    ]

    msg = f"{rnd.choice(starters)} {rnd.choice(mids)} {rnd.choice(ends)}"
    if trace:
        return {
            "text": msg,
            "engine": "fallback",
            "trace": {
                "engine": ENGINE,
                "meta_keys": sorted(list(meta.keys())),
                "note": "fallback wrapper active",
            },
        }
    return msg


def reason(text: str, trace: bool = False, meta: Dict[str, Any] | None = None) -> Any:
    """
    Public API expected by main/core.py

    IMPORTANT: This function MUST exist.
    Later you can switch ENGINE to real backends (LLM, RAG, etc.).
    """
    # For now: only fallback implemented (guaranteed working)
    return _fallback_reason(text=text, trace=trace, meta=meta)
