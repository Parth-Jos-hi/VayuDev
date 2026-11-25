from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError,SQLAlchemyError
from app.db.models.users import User
from app.schemas.users import UserUpdate
def get_user_by_id(db:Session,user_id:None)-> User|None:
    user = db.get(User,user_id) 
    return user
def get_or_create_user(db:Session,user_id:None)->User:
    user = db.get(User,user_id)
    if user is not None:
        return user
    try:
        new_user = User(id = user_id)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except IntegrityError:
        db.rollback()
        existing_user = get_user_by_id(db,user_id)
        if existing_user is not None:
            return existing_user
        raise
    except SQLAlchemyError:
        db.rollback()
        raise
def update_user_profile(db:Session,user:User ,profile_data:UserUpdate)->User:
    update_data = profile_data.model_dump(exclude_unset = True)
    if not update_data: 
        return user
    try:
        if "display_name" in update_data:
            user.display_name = update_data["display_name"]
            db.commit()
            db.refresh(user)
            return user     
    except SQLAlchemyError:
        db.rollback()
        raise
    

