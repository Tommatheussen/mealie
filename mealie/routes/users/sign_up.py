import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from mealie.core.security import get_password_hash
from mealie.db.database import db
from mealie.db.db_setup import generate_session
from mealie.routes.deps import get_current_user
from mealie.schema.sign_up import SignUpIn, SignUpOut, SignUpToken
from mealie.schema.user import UserIn, UserInDB
from mealie.services.events import create_user_event
from sqlalchemy.orm.session import Session

router = APIRouter(prefix="/api/users/sign-ups", tags=["User Signup"])


@router.get("", response_model=list[SignUpOut])
async def get_all_open_sign_ups(
    current_user=Depends(get_current_user),
    session: Session = Depends(generate_session),
):
    """ Returns a list of open sign up links """

    return db.sign_ups.get_all(session)


@router.post("", response_model=SignUpToken)
async def create_user_sign_up_key(
    background_tasks: BackgroundTasks,
    key_data: SignUpIn,
    current_user: UserInDB = Depends(get_current_user),
    session: Session = Depends(generate_session),
):
    """ Generates a Random Token that a new user can sign up with """

    if not current_user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    sign_up = {
        "token": str(uuid.uuid1().hex),
        "name": key_data.name,
        "admin": key_data.admin,
    }

    background_tasks.add_task(
        create_user_event, "Sign-up Token Created", f"Created by {current_user.full_name}", session=session
    )
    return db.sign_ups.create(session, sign_up)


@router.post("/{token}")
async def create_user_with_token(
    background_tasks: BackgroundTasks,
    token: str,
    new_user: UserIn,
    session: Session = Depends(generate_session),
):
    """ Creates a user with a valid sign up token """

    # Validate Token
    db_entry: SignUpOut = db.sign_ups.get(session, token, limit=1)
    if not db_entry:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    # Create User
    new_user.admin = db_entry.admin
    new_user.password = get_password_hash(new_user.password)
    db.users.create(session, new_user.dict())

    # DeleteToken
    background_tasks.add_task(
        create_user_event, "Sign-up Token Used", f"New User {new_user.full_name}", session=session
    )
    db.sign_ups.delete(session, token)


@router.delete("/{token}")
async def delete_token(
    token: str,
    current_user: UserInDB = Depends(get_current_user),
    session: Session = Depends(generate_session),
):
    """ Removed a token from the database """
    if not current_user.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    db.sign_ups.delete(session, token)
