from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional


EventType = Literal[
    "node_execution",
    "verification_result",
    "vicdan_decision",
    "goal_decision",
    "human_feedback",
    "resource_allocation",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_did_document(name: str | None = None) -> dict[str, str]:
    private_key = secrets.token_hex(32)
    public_key = sha256_text(private_key)
    suffix_seed = f"{name or 'actor'}:{public_key}"
    did = f"did:hope:{sha256_text(suffix_seed)[:24]}"
    return {
        "did": did,
        "public_key": public_key,
        "private_key": private_key,
    }


def sign_payload(payload: dict[str, Any], private_key: str) -> str:
    return sha256_text(canonical_json(payload) + private_key)


@dataclass
class DIDIdentity:
    did: str
    name: str
    actor_type: str
    public_key: str
    private_key: str
    created_at: str = field(default_factory=utc_now)


@dataclass
class ContributionEvent:
    event_id: str
    trace_id: Optional[str]
    actor_did: str
    actor_name: str
    actor_type: str
    event_type: EventType
    payload: dict[str, Any]
    impact_score: float = 0.0
    trust_delta: float = 0.0
    signature: str = ""
    created_at: str = field(default_factory=utc_now)


@dataclass
class ChainRecord:
    chain_index: int
    record_id: str
    prev_hash: str
    record_hash: str
    event_id: str
    created_at: str


@dataclass
class ReputationState:
    actor_did: str
    actor_name: str
    actor_type: str
    reputation_score: float
    trust_score: float
    contribution_count: int
    last_event_at: str


class HOPEChainDB:
    def __init__(self, db_path: str = "hopechain_did.db") -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS did_identities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    did TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    public_key TEXT NOT NULL,
                    private_key TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS contribution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE NOT NULL,
                    trace_id TEXT,
                    actor_did TEXT NOT NULL,
                    actor_name TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    impact_score REAL NOT NULL,
                    trust_delta REAL NOT NULL,
                    signature TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chain_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chain_index INTEGER UNIQUE NOT NULL,
                    record_id TEXT UNIQUE NOT NULL,
                    prev_hash TEXT NOT NULL,
                    record_hash TEXT UNIQUE NOT NULL,
                    event_id TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reputation_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_did TEXT UNIQUE NOT NULL,
                    actor_name TEXT NOT NULL,
                    actor_type TEXT NOT NULL,
                    reputation_score REAL NOT NULL,
                    trust_score REAL NOT NULL,
                    contribution_count INTEGER NOT NULL,
                    last_event_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    def create_identity(self, name: str, actor_type: str) -> DIDIdentity:
        doc = generate_did_document(name)
        identity = DIDIdentity(
            did=doc["did"],
            name=name,
            actor_type=actor_type,
            public_key=doc["public_key"],
            private_key=doc["private_key"],
        )
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO did_identities (
                    did, name, actor_type, public_key, private_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.did,
                    identity.name,
                    identity.actor_type,
                    identity.public_key,
                    identity.private_key,
                    identity.created_at,
                ),
            )
            conn.commit()
            return identity
        finally:
            conn.close()

    def get_identity(self, did: str) -> Optional[DIDIdentity]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM did_identities WHERE did = ?",
                (did,),
            ).fetchone()
            if not row:
                return None
            return DIDIdentity(
                did=row["did"],
                name=row["name"],
                actor_type=row["actor_type"],
                public_key=row["public_key"],
                private_key=row["private_key"],
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def get_identity_by_name(self, name: str) -> Optional[DIDIdentity]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM did_identities WHERE name = ?",
                (name,),
            ).fetchone()
            if not row:
                return None
            return DIDIdentity(
                did=row["did"],
                name=row["name"],
                actor_type=row["actor_type"],
                public_key=row["public_key"],
                private_key=row["private_key"],
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def ensure_identity(self, name: str, actor_type: str) -> DIDIdentity:
        existing = self.get_identity_by_name(name)
        if existing:
            return existing
        return self.create_identity(name=name, actor_type=actor_type)

    def append_event(self, event: ContributionEvent) -> ChainRecord:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO contribution_events (
                    event_id, trace_id, actor_did, actor_name, actor_type,
                    event_type, payload_json, impact_score, trust_delta,
                    signature, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.trace_id,
                    event.actor_did,
                    event.actor_name,
                    event.actor_type,
                    event.event_type,
                    canonical_json(event.payload),
                    event.impact_score,
                    event.trust_delta,
                    event.signature,
                    event.created_at,
                ),
            )

            last = conn.execute(
                "SELECT * FROM chain_records ORDER BY chain_index DESC LIMIT 1"
            ).fetchone()

            if last:
                prev_hash = last["record_hash"]
                chain_index = int(last["chain_index"]) + 1
            else:
                prev_hash = "GENESIS"
                chain_index = 0

            material = canonical_json(
                {
                    "chain_index": chain_index,
                    "prev_hash": prev_hash,
                    "event_id": event.event_id,
                    "actor_did": event.actor_did,
                    "actor_name": event.actor_name,
                    "actor_type": event.actor_type,
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "impact_score": event.impact_score,
                    "trust_delta": event.trust_delta,
                    "signature": event.signature,
                    "created_at": event.created_at,
                }
            )
            record_hash = sha256_text(material)
            record_id = generate_id("rec")

            conn.execute(
                """
                INSERT INTO chain_records (
                    chain_index, record_id, prev_hash, record_hash, event_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chain_index,
                    record_id,
                    prev_hash,
                    record_hash,
                    event.event_id,
                    event.created_at,
                ),
            )

            self._upsert_reputation_tx(conn, event)

            conn.commit()

            return ChainRecord(
                chain_index=chain_index,
                record_id=record_id,
                prev_hash=prev_hash,
                record_hash=record_hash,
                event_id=event.event_id,
                created_at=event.created_at,
            )
        finally:
            conn.close()

    def _upsert_reputation_tx(self, conn: sqlite3.Connection, event: ContributionEvent) -> None:
        row = conn.execute(
            "SELECT * FROM reputation_states WHERE actor_did = ?",
            (event.actor_did,),
        ).fetchone()

        if row:
            reputation = float(row["reputation_score"])
            trust = float(row["trust_score"])
            count = int(row["contribution_count"])
        else:
            reputation = 0.5
            trust = 0.5
            count = 0

        reputation = max(0.0, min(1.0, reputation + (event.impact_score * 0.08)))
        trust = max(0.0, min(1.0, trust + event.trust_delta))
        count += 1

        conn.execute(
            """
            INSERT INTO reputation_states (
                actor_did, actor_name, actor_type, reputation_score,
                trust_score, contribution_count, last_event_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(actor_did) DO UPDATE SET
                actor_name=excluded.actor_name,
                actor_type=excluded.actor_type,
                reputation_score=excluded.reputation_score,
                trust_score=excluded.trust_score,
                contribution_count=excluded.contribution_count,
                last_event_at=excluded.last_event_at
            """,
            (
                event.actor_did,
                event.actor_name,
                event.actor_type,
                reputation,
                trust,
                count,
                event.created_at,
            ),
        )

    def list_recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT ce.*, cr.chain_index, cr.prev_hash, cr.record_hash
                FROM contribution_events ce
                LEFT JOIN chain_records cr ON cr.event_id = ce.event_id
                ORDER BY ce.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            items: list[dict[str, Any]] = []
            for row in rows:
                item = dict(row)
                item["payload"] = json.loads(item.pop("payload_json"))
                items.append(item)
            return items
        finally:
            conn.close()

    def get_reputation(self, actor_did: str) -> Optional[ReputationState]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM reputation_states WHERE actor_did = ?",
                (actor_did,),
            ).fetchone()
            if not row:
                return None
            return ReputationState(
                actor_did=row["actor_did"],
                actor_name=row["actor_name"],
                actor_type=row["actor_type"],
                reputation_score=row["reputation_score"],
                trust_score=row["trust_score"],
                contribution_count=row["contribution_count"],
                last_event_at=row["last_event_at"],
            )
        finally:
            conn.close()

    def verify_chain(self) -> dict[str, Any]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT cr.chain_index, cr.prev_hash, cr.record_hash, cr.event_id,
                       ce.actor_did, ce.actor_name, ce.actor_type, ce.event_type,
                       ce.payload_json, ce.impact_score, ce.trust_delta, ce.signature, ce.created_at
                FROM chain_records cr
                JOIN contribution_events ce ON ce.event_id = cr.event_id
                ORDER BY cr.chain_index ASC
                """
            ).fetchall()

            prev_hash = "GENESIS"
            checked = 0

            for row in rows:
                material = canonical_json(
                    {
                        "chain_index": row["chain_index"],
                        "prev_hash": row["prev_hash"],
                        "event_id": row["event_id"],
                        "actor_did": row["actor_did"],
                        "actor_name": row["actor_name"],
                        "actor_type": row["actor_type"],
                        "event_type": row["event_type"],
                        "payload": json.loads(row["payload_json"]),
                        "impact_score": row["impact_score"],
                        "trust_delta": row["trust_delta"],
                        "signature": row["signature"],
                        "created_at": row["created_at"],
                    }
                )
                recomputed = sha256_text(material)

                if row["prev_hash"] != prev_hash:
                    return {
                        "ok": False,
                        "checked_records": checked,
                        "error": f"Broken prev_hash at chain_index {row['chain_index']}",
                    }

                if row["record_hash"] != recomputed:
                    return {
                        "ok": False,
                        "checked_records": checked,
                        "error": f"Hash mismatch at chain_index {row['chain_index']}",
                    }

                prev_hash = row["record_hash"]
                checked += 1

            return {"ok": True, "checked_records": checked}
        finally:
            conn.close()

    def verify_event_signature(self, event_id: str) -> dict[str, Any]:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT ce.*, di.private_key
                FROM contribution_events ce
                JOIN did_identities di ON di.did = ce.actor_did
                WHERE ce.event_id = ?
                """,
                (event_id,),
            ).fetchone()

            if not row:
                return {"ok": False, "error": "Event not found"}

            payload = json.loads(row["payload_json"])
            signable = {
                "event_id": row["event_id"],
                "trace_id": row["trace_id"],
                "actor_did": row["actor_did"],
                "actor_name": row["actor_name"],
                "actor_type": row["actor_type"],
                "event_type": row["event_type"],
                "payload": payload,
                "impact_score": row["impact_score"],
                "trust_delta": row["trust_delta"],
                "created_at": row["created_at"],
            }
            recomputed = sign_payload(signable, row["private_key"])

            return {
                "ok": recomputed == row["signature"],
                "event_id": row["event_id"],
                "actor_did": row["actor_did"],
                "stored_signature": row["signature"],
                "recomputed_signature": recomputed,
            }
        finally:
            conn.close()


class HOPEChain:
    def __init__(self, db_path: str = "hopechain_did.db") -> None:
        self.db = HOPEChainDB(db_path)

    def ensure_actor(self, actor_name: str, actor_type: str) -> DIDIdentity:
        return self.db.ensure_identity(name=actor_name, actor_type=actor_type)

    def _build_signed_event(
        self,
        identity: DIDIdentity,
        trace_id: Optional[str],
        event_type: EventType,
        payload: dict[str, Any],
        impact_score: float,
        trust_delta: float,
    ) -> ContributionEvent:
        event_id = generate_id("evt")
        created_at = utc_now()

        signable = {
            "event_id": event_id,
            "trace_id": trace_id,
            "actor_did": identity.did,
            "actor_name": identity.name,
            "actor_type": identity.actor_type,
            "event_type": event_type,
            "payload": payload,
            "impact_score": impact_score,
            "trust_delta": trust_delta,
            "created_at": created_at,
        }
        signature = sign_payload(signable, identity.private_key)

        return ContributionEvent(
            event_id=event_id,
            trace_id=trace_id,
            actor_did=identity.did,
            actor_name=identity.name,
            actor_type=identity.actor_type,
            event_type=event_type,
            payload=payload,
            impact_score=impact_score,
            trust_delta=trust_delta,
            signature=signature,
            created_at=created_at,
        )

    def record_node_execution(
        self,
        trace_id: str,
        actor_name: str,
        output_preview: str,
        confidence: float,
        duration_ms: int,
        success: bool = True,
    ) -> dict[str, Any]:
        identity = self.ensure_actor(actor_name=actor_name, actor_type="node")
        impact = max(0.0, min(1.0, confidence))
        trust_delta = 0.03 if success else -0.05

        payload = {
            "output_preview": output_preview[:220],
            "confidence": confidence,
            "duration_ms": duration_ms,
            "success": success,
        }
        event = self._build_signed_event(
            identity=identity,
            trace_id=trace_id,
            event_type="node_execution",
            payload=payload,
            impact_score=impact,
            trust_delta=trust_delta,
        )
        record = self.db.append_event(event)
        rep = self.db.get_reputation(identity.did)
        verify = self.db.verify_event_signature(event.event_id)
        return {
            "identity": asdict(identity),
            "event": asdict(event),
            "record": asdict(record),
            "reputation": asdict(rep) if rep else None,
            "signature_verify": verify,
        }

    def record_goal_decision(
        self,
        trace_id: str,
        actor_name: str,
        goal_id: str,
        rank: int,
        expected_impact: float,
        vicdan_alignment: str,
    ) -> dict[str, Any]:
        identity = self.ensure_actor(actor_name=actor_name, actor_type="planner")
        trust_delta = 0.04 if vicdan_alignment == "ACCEPT" else 0.01

        payload = {
            "goal_id": goal_id,
            "rank": rank,
            "expected_impact": expected_impact,
            "vicdan_alignment": vicdan_alignment,
        }
        event = self._build_signed_event(
            identity=identity,
            trace_id=trace_id,
            event_type="goal_decision",
            payload=payload,
            impact_score=expected_impact,
            trust_delta=trust_delta,
        )
        record = self.db.append_event(event)
        rep = self.db.get_reputation(identity.did)
        verify = self.db.verify_event_signature(event.event_id)
        return {
            "identity": asdict(identity),
            "event": asdict(event),
            "record": asdict(record),
            "reputation": asdict(rep) if rep else None,
            "signature_verify": verify,
        }

    def record_human_feedback(
        self,
        trace_id: str,
        actor_name: str,
        target_actor_name: str,
        rating: float,
        note: str = "",
    ) -> dict[str, Any]:
        target_identity = self.ensure_actor(actor_name=target_actor_name, actor_type="node")
        self.ensure_actor(actor_name=actor_name, actor_type="human")

        impact = max(0.0, min(1.0, rating))
        trust_delta = (rating - 0.5) * 0.2

        payload = {
            "feedback_from": actor_name,
            "rating": rating,
            "note": note[:300],
        }
        event = self._build_signed_event(
            identity=target_identity,
            trace_id=trace_id,
            event_type="human_feedback",
            payload=payload,
            impact_score=impact,
            trust_delta=trust_delta,
        )
        record = self.db.append_event(event)
        rep = self.db.get_reputation(target_identity.did)
        verify = self.db.verify_event_signature(event.event_id)
        return {
            "identity": asdict(target_identity),
            "event": asdict(event),
            "record": asdict(record),
            "reputation": asdict(rep) if rep else None,
            "signature_verify": verify,
        }


if __name__ == "__main__":
    chain = HOPEChain("hopechain_did.db")

    node_result = chain.record_node_execution(
        trace_id=generate_id("trace"),
        actor_name="local-1",
        output_preview="Local node generated a structured answer.",
        confidence=0.72,
        duration_ms=41,
        success=True,
    )

    planner_result = chain.record_goal_decision(
        trace_id=generate_id("trace"),
        actor_name="hopecore",
        goal_id="goal_food_001",
        rank=1,
        expected_impact=0.96,
        vicdan_alignment="ACCEPT",
    )

    feedback_result = chain.record_human_feedback(
        trace_id=generate_id("trace"),
        actor_name="erhan",
        target_actor_name="local-1",
        rating=0.91,
        note="Strong output quality and good alignment.",
    )

    print(json.dumps(
        {
            "node_result": node_result,
            "planner_result": planner_result,
            "feedback_result": feedback_result,
            "recent_events": chain.db.list_recent_events(limit=10),
            "chain_verify": chain.db.verify_chain(),
        },
        indent=2,
    ))
