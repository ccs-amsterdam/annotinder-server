from typing import Optional
from authlib.jose import JsonWebSignature

from amcat4annotator.db import User

SECRET_KEY="not very secret, sorry"

def get_token(user: User) -> str:
    return JsonWebSignature().serialize_compact(
        protected={'alg': 'HS256'},
        payload=user.email.encode("utf-8"),
        key=SECRET_KEY).decode("ascii")

def verify_token(token: str) -> User:
    payload = JsonWebSignature().deserialize_compact(token, SECRET_KEY)
    email = payload['payload'].decode("utf-8")
    return User.get(User.email == email)
