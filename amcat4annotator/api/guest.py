import hashlib

from fastapi import APIRouter, HTTPException, status
from fastapi.params import Query

from amcat4annotator import auth
from amcat4annotator.db import User
from amcat4annotator.auth import verify_jobtoken

app_annotator_guest = APIRouter(prefix ='/guest', tags=["annotator guest"])

@app_annotator_guest.get("/jobtoken")
def redeem_job_token(token: str = Query(None, description="A token for getting access to a specific coding job"),
                     user_id: str = Query(None, description="Optional, a user ID")):
    """
    Convert a job token into a 'normal' token.
    Should be called with a token and optional user_id argument
    """
    job = verify_jobtoken(token)
    if not job:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Job token not valid")
    if not user_id:
        x = hashlib.sha1()
        x.update(str(User.select().count()).encode('utf-8'))
        user_id = x.hexdigest()
    email = f"jobuser__{job.id}__{user_id}"
    user = User.get_or_none(User.email == email)
    if not user:
        user = User.create(email=email, restricted_job=job)
    return {"token": auth.get_token(user),
            "job_id": job.id,
            "email": user.email,
            "is_admin": user.is_admin}
