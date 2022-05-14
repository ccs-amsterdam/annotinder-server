import json
import logging
from typing import Optional

from authlib.jose import JsonWebSignature
import bcrypt
from authlib.jose.errors import DecodeError

from fastapi import HTTPException
from fastapi.params import Depends
from fastapi.security import OAuth2PasswordBearer


from sqlalchemy.orm import Session

from amcat4annotator.models import User, CodingJob, JobUser
from amcat4annotator.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/users/me/token")

SECRET_KEY = "not very secret, sorry"

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
        key=SECRET_KEY).decode("ascii")


def get_token(user: User) -> str:
    t = _get_token(payload={'user': user.email})
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
        payload = JsonWebSignature().deserialize_compact(token, SECRET_KEY)
    except DecodeError:
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
    u = db.query(User).filter(User.email == payload['user']).first()
    if not u:
        logging.warning("User does not exist")
        return None
    return u



def check_job_user(db: Session, user: User, job: CodingJob):
    if user.restricted_job is not None:
        if user.restricted_job != job.id: 
            raise HTTPException(status_code=401, detail="User not authorized to code job")
    else:      
        if job.restricted:
            if not db.query(JobUser).filter(JobUser.user_id == user.id, JobUser.codingjob_id == job.id, JobUser.can_code == True).first():
                raise HTTPException(status_code=401, detail="User not authorized to code job")
    

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





