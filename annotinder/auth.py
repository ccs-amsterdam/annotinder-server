import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

from authlib.jose import JsonWebSignature
import bcrypt
from authlib.jose.errors import DecodeError, BadSignatureError

from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from annotinder.models import User, CodingJob, JobUser
from annotinder.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/me/token")

load_dotenv()
ENV_SECRET_KEY = os.getenv('SECRET_KEY') 

def secret_key():
    if ENV_SECRET_KEY is None:
        raise NotImplementedError('A .env file with a SECRET_KEY needs to be created. You can run: "python -m annotinder create_env"')
    return ENV_SECRET_KEY

async def auth_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    user = verify_token(db, token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")
    return user


def check_admin(user: User):
    if not user.is_admin:
        raise HTTPException(status_code=401, detail="Admin rights required")


def _get_token(payload: dict) -> str:
    return JsonWebSignature().serialize_compact(
        protected={'alg': 'HS256'},
        payload=json.dumps(payload).encode('utf-8'),
        key=secret_key()).decode("ascii")


def get_token(user: User) -> str:
    t = _get_token(payload={'user': user.name})
    if not t:
        logging.warning('Could not create token')
        return None
    return t


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, db_password: str):  
    return bcrypt.checkpw(password.encode("utf-8"), db_password.encode("utf-8"))


def _verify_token(token: str) -> Optional[dict]:
    try:
        payload = JsonWebSignature().deserialize_compact(token, secret_key())
    except (BadSignatureError, DecodeError):
        return None
    return json.loads(payload['payload'].decode("utf-8"))


def verify_token(db: Session, token: str = Depends(oauth2_scheme)) -> Optional[User]:
    """
    Verify the given token, returning the authenticated User

    If the token is invalid, expired, or the user does not exist, returns None
    """
    payload = _verify_token(token)
    if payload is None or 'user' not in payload:
        logging.warning("Invalid payload")
        return None
    u = db.query(User).filter(User.name == payload['user']).first()
    if not u:
        logging.warning("User does not exist")
        return None
    return u


def get_jobtoken(job: CodingJob) -> str:
    return _get_token(payload={'job': job.id})


def verify_jobtoken(db: Session, token: str) -> Optional[CodingJob]:
    """
    Verify the given job token, returning the job
    If the token is invalid, expired, or the user does not exist, returns None
    """
    payload = _verify_token(token)
    if payload is None or 'job' not in payload:
        return None
    return db.query(CodingJob).filter(CodingJob.id == payload['job']).first()





