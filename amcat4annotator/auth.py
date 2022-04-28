import json
import logging
from typing import Optional

from authlib.jose import JsonWebSignature
import bcrypt
from authlib.jose.errors import DecodeError
from flask_httpauth import HTTPBasicAuth, HTTPTokenAuth, MultiAuth, g
from werkzeug.exceptions import Unauthorized

from amcat4annotator.db import User, CodingJob, JobUser

SECRET_KEY = "not very secret, sorry"

basic_auth = HTTPBasicAuth()
token_auth = HTTPTokenAuth()
multi_auth = MultiAuth(basic_auth, token_auth)


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


def check_admin(job: Optional[CodingJob]=None):
    if not g.current_user.is_admin:
        raise Unauthorized("Admin rights required")
    
def check_job_owner(job: CodingJob):
    if not JobUser.select().where((JobUser.user == g.current_user) & (JobUser.job == job) & (JobUser.is_owner == True)).exists():
        raise Unauthorized("User not authorized to manage job")

def check_job_user(job: CodingJob):
    if g.current_user.restricted_job is not None:
        if g.current_user.restricted_job != job.id: 
            raise Unauthorized("User not authorized to code job")
    else:      
        if job.restricted and not JobUser.select().where((JobUser.user == g.current_user) & (JobUser.job == job)).exists():
            raise Unauthorized("User not authorized to code job")
