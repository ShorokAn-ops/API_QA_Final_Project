from sqlalchemy.orm import Session
from models.sync_state import SyncState


def get_state(db: Session, key: str) -> str | None:
    row = db.query(SyncState).filter(SyncState.key == key).first()
    return row.value if row else None


def set_state(db: Session, key: str, value: str | None) -> None:
    row = db.query(SyncState).filter(SyncState.key == key).first()
    if not row:
        row = SyncState(key=key, value=value)
        db.add(row)
    else:
        row.value = value
    db.commit()
