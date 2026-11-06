"""A user's permanent memory: list and delete what they asked the assistant to remember ("save it")."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models.user import User
from backend.app.models.user_memory import UserMemory
from backend.app.security.auth import get_current_user
from backend.app.services import user_memory

router = APIRouter(prefix="/memories", tags=["Memory"])


def _out(memory: UserMemory) -> dict:
    return {"id": memory.id, "content": memory.content,
            "created_at": memory.created_at.isoformat() if memory.created_at else None}


@router.get("")
def list_memories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_out(memory) for memory in user_memory.list_memories(db, current_user.id)]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(memory_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    memory = db.query(UserMemory).filter(UserMemory.id == memory_id, UserMemory.user_id == current_user.id).first()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    db.delete(memory)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_memories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(UserMemory).filter(UserMemory.user_id == current_user.id).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
