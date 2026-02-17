import uuid
import hashlib
from sqlalchemy.orm import Session
from app.identity.models import Identity


def generate_did() -> str:
    """
    Generate canonical DID:
    did:hope:app:{sha256(uuid4)}
    """
    raw_uuid = str(uuid.uuid4())
    sha = hashlib.sha256(raw_uuid.encode()).hexdigest()
    return f"did:hope:app:{sha}"


def create_identity(db: Session) -> Identity:
    """
    Create new Identity record and persist to DB.
    """
    did = generate_did()

    identity = Identity(did=did)

    db.add(identity)
    db.commit()
    db.refresh(identity)

    return identity
