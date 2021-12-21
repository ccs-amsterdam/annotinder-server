import logging
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


def verify_token(token: str) -> User:
    payload = JsonWebSignature().deserialize_compact(token, SECRET_KEY)
    email = payload['payload'].decode("utf-8")
    return User.get(User.email == email)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def check_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("ascii"))


@basic_auth.verify_password
def app_verify_password(username, password):
    u = User.get_or_none(User.email == username)
    if not u:
        logging.warning(f"User {u} does not exist")
    elif not u.password:
        logging.warning(f"User {u} has no password specified")
    elif not check_password(password, u.password):
        logging.warning(f"Password for {u} did not match")
    else:
        g.current_user = u
        return True


@token_auth.verify_token
def app_verify_token(token):
    try:
        u = verify_token(token)
    except DecodeError as e:
        logging.error(f"Invalid token {token!r}: {e}")
        return
    g.current_user = u
    return True


def check_admin():
    if not g.current_user.is_admin:
        raise Unauthorized("Admin rights required")
