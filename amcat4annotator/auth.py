import json
import logging
from typing import Optional

from authlib.jose import JsonWebSignature
import bcrypt
from authlib.jose.errors import DecodeError

from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer

from amcat4annotator.db import User, CodingJob, JobUser

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/me/token")


SECRET_KEY = "not very secret, sorry"


async def authenticated_user(token: str = Depends(oauth2_scheme)) -> User:
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid token")
    return user

def check_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=401, detail="Admin rights required")

def check_job_owner(user: User, job: CodingJob):
    if not JobUser.select().where((JobUser.user == user) & (JobUser.job == job) & (JobUser.is_owner == True)).exists():
        raise HTTPException(status_code=401, detail="User not authorized to manage job")

def check_job_user(user: User, job: CodingJob):
    if user.restricted_job is not None:
        if user.restricted_job != job.id: 
            raise HTTPException(status_code=401, detail="User not authorized to code job")
    else:      
        if job.restricted and not JobUser.select().where(JobUser.user == user, JobUser.job == job, JobUser.can_code == True).exists():
            raise HTTPException(status_code=401, detail="User not authorized to code job")




def verify_password(username, password):
    u = User.get_or_none(User.email == username)
    if not u:
        logging.warning(f"User {u} does not exist")
        return None
    elif not u.password:
        logging.warning(f"Password for {u} is missing")
        return None
    elif not bcrypt.checkpw(password.encode("utf-8"), u.password.encode("utf-8")):
        logging.warning(f"Password for {u} did not match")
        return None
    else:
        return u


def _get_token(payload: dict) -> str:
    return JsonWebSignature().serialize_compact(
        protected={'alg': 'HS256'},
        payload=json.dumps(payload).encode('utf-8'),
        key=SECRET_KEY).decode("ascii")


def get_token(user: User) -> str:
    return _get_token(payload={'user': user.email})


def get_jobtoken(job: CodingJob) -> str:
    return _get_token(payload={'job': job.id})


def _verify_token(token: str) -> Optional[dict]:
    try:
        payload = JsonWebSignature().deserialize_compact(token, SECRET_KEY)
    except DecodeError:
        return None
    return json.loads(payload['payload'].decode("utf-8"))


def verify_token(token: str) -> Optional[User]:
    """
    Verify the given token, returning the authenticated User

    If the token is invalid, expired, or the user does not exist, returns None
    """
    payload = _verify_token(token)
    if payload is None or 'user' not in payload:
        return None
    return User.get_or_none(User.email == payload['user'])


def verify_jobtoken(token: str) -> Optional[CodingJob]:
    """
    Verify the given job token, returning the job
    If the token is invalid, expired, or the user does not exist, returns None
    """
    payload = _verify_token(token)
    if payload is None or 'job' not in payload:
        return None
    return CodingJob.get_or_none(CodingJob.id == payload['job'])


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def change_password(user: User, password: str):
    user.password = hash_password(password)
    user.save()



