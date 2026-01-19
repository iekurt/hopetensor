# ============================================================
# HOPEtensor — Runtime Signature Engine
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

import hashlib
import subprocess
from datetime import datetime


# ------------------------------------------------------------------
# KANONİK İMZA (MARKA + MANİFESTO — DEĞİŞMEZ)
# ------------------------------------------------------------------
CANONICAL_SIGNATURE = """
HOPEtensor — Reasoning Infrastructure
Author        : Erhan (master)
Digital Twin  : Vicdan
License       : Proprietary / HOPE Ecosystem
"Yurtta barış, Cihanda barış"
"In GOD We HOPE"
""".strip()


# ------------------------------------------------------------------
# GIT COMMIT ID
# ------------------------------------------------------------------
def git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "nogit"


# ------------------------------------------------------------------
# İMZA HASH
# ------------------------------------------------------------------
def signature_hash() -> str:
    return hashlib.sha256(
        CANONICAL_SIGNATURE.encode("utf-8")
    ).hexdigest()


# ------------------------------------------------------------------
# RUNTIME SIGNATURE (TEK KAYNAK GERÇEK)
# ------------------------------------------------------------------
def runtime_signature(version: str) -> dict:
    return {
        "app": "HOPEtensor",
        "brand": "HOPEtensor",
        "author": "Erhan (master)",
        "digital_twin": "Vicdan",
        "version": version,
        "commit": git_commit(),
        "created": "2026-01-19",
        "runtime_utc": datetime.utcnow().isoformat() + "Z",
        "signature_hash": signature_hash(),
    }


# ------------------------------------------------------------------
# LOCAL TEST
# ------------------------------------------------------------------
if __name__ == "__main__":
    import json
    print(json.dumps(runtime_signature("0.1.0"), indent=2))
