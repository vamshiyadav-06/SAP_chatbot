from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.shared_prompt import SharedPrompt

# Public, unauthenticated: anyone holding a share token may read that one prompt.
router = APIRouter(prefix="/shared", tags=["Shared"])


@router.get("/prompts/{token}")
def get_shared_prompt(token: str, db: Session = Depends(get_db)):
    shared = db.query(SharedPrompt).filter(SharedPrompt.token == token, SharedPrompt.revoked.is_(False)).first()
    if not shared:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared prompt not found")
    return {"content": shared.content, "answer": shared.answer, "created_at": shared.created_at}
