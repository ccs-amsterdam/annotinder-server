import logging
from typing import Optional

from authlib.jose import JsonWebSignature
import bcrypt
from authlib.jose.errors import DecodeError
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth, g
from werkzeug.exceptions import Unauthorized

from amcat4annotator.db import User

SECRET_KEY = "not very secret, sorry"

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


def get_token(user: User) -> str:
    return JsonWebSignature().serialize_compact(
        protected={'alg': 'HS256'},
        payload=user.email.encode("utf-8"),
        key=SECRET_KEY).decode("ascii")


def verify_token(token: str) -> Optional[User]:
    """
    Verify the given token, returning the authenticated User

    If the token is invalid, expired, or the user does not exist, returns None
    """
    try:
        payload = JsonWebSignature().deserialize_compact(token, SECRET_KEY)
    except DecodeError:
        return None

    email = payload['payload'].decode("utf-8")
    return User.get_or_none(User.email == email)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(user: User, password: str) -> bool:
    if not user.password:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), user.password.encode("ascii"))


def change_password(user: User, password: str):
    user.password = hash_password(password)
    user.save()


@basic_auth.verify_password
def app_verify_password(username, password):
    u = User.get_or_none(User.email == username)
    if not u:
        logging.warning(f"User {u} does not exist")
    elif not verify_password(u, password):
        logging.warning(f"Password for {u} did not match")
    else:
        g.current_user = u
        return True


@token_auth.verify_token
def app_verify_token(token) -> bool:
    u = verify_token(token)
    g.current_user = u
    return bool(u)


def check_admin():
    if not g.current_user.is_admin:
        raise Unauthorized("Admin rights required")
