import hashlib

from fastapi import APIRouter, HTTPException, status
from fastapi.params import Query, Depends

from sqlalchemy.orm import Session

from annotinder.crud import crud_user
from annotinder.database import engine, get_db
from annotinder.auth import verify_jobtoken, get_token
from annotinder.models import User


app_annotator_guest = APIRouter(prefix='/guest', tags=["annotator guest"])


## create another version that authenticates via token, and then only adds jobuser without creating new user

@app_annotator_guest.get("/jobtoken")
def redeem_job_token(token: str = Query(None, description="A token for getting access to a specific coding job"),
                     user_id: str = Query(None, description="Optional, a user ID"),
                     db: Session = Depends(get_db)):
    """
    Convert a job token into a 'normal' token.
    Should be called with a token and optional user_id argument
    """
    job = verify_jobtoken(db, token)
    if not job:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Job token not valid")
    
    user = crud_user.create_guest_user(db, user_id, restricted_job=job.id)
    return {"token": get_token(user)}


