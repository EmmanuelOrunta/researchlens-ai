# services/auth_service.py
#
# Small, atomic building blocks for authentication: hashing/checking passwords and
# reading/writing User rows. The step-by-step "what happens when the register form is
# submitted" logic (validation, checking for duplicate emails, etc.) lives in
# routes/auth_routes.py instead, so you can read that file top-to-bottom and see the
# whole flow in one place.

import bcrypt
from models.user import User


def hash_password(password: str) -> str:
    """
    Turn a plain-text password into a bcrypt hash. bcrypt automatically adds a random
    "salt", so two users with the same password still get completely different hashes.
    We NEVER store the plain-text password anywhere.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check a plain-text password against a stored bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def get_user_by_email(session, email: str):
    """Return the User with this email, or None if no such user exists."""
    return session.query(User).filter(User.email == email).first()


def get_user_by_id(session, user_id: int):
    """Return the User with this id, or None. Used by the Settings page."""
    return session.query(User).filter(User.id == user_id).first()


def create_user(session, name: str, email: str, password_hash: str) -> User:
    """Insert a new user row and return it."""
    user = User(name=name, email=email, password_hash=password_hash)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user_name(session, user: User, name: str) -> User:
    """Change the display name on an existing account (the Settings page's Profile card)."""
    user.name = name
    session.commit()
    return user


def update_user_password(session, user: User, new_password: str) -> User:
    """
    Overwrite an existing account's password hash. The caller (routes/settings_routes.py)
    is responsible for checking the user's *current* password with verify_password()
    before calling this - this function just does the write, same division of labour as
    auth_routes.py handling validation and this file handling the actual hashing/storage.
    """
    user.password_hash = hash_password(new_password)
    session.commit()
    return user
