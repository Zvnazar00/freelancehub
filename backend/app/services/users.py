from sqlalchemy.orm import Session

from app.models import User
from app.schemas.auth import UserUpdate


def update_profile(db: Session, user: User, data: UserUpdate) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user
