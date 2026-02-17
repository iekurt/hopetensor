from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.identity.service import create_identity

router = APIRouter()


@router.post("/create")
def create_did(db: Session = Depends(get_db)):
    identity = create_identity(db)

    return {
        "ok": True,
        "request_id": str(identity.id),
        "result": {
            "did": identity.did,
            "created_at": identity.created_at.isoformat()
        }
    }