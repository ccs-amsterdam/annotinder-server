import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from fastapi.params import Query, Depends
from sqlalchemy.orm import Session
from annotinder.database import engine, get_db
from annotinder.models import User

load_dotenv()


app_annotator_host = APIRouter(prefix='/host', tags=["annotator host"])

@app_annotator_host.get("")
def get_host_info(db: Session = Depends(get_db), email: str = Query(None, description="Email address of an existing user")):
    """
    Get information about a host server. If email argument is given, also returns (non sensitive) information
    about this user that is relevant for login process (e.g., whether a password exists, whether an admin)
    """
    github = dict(client_id = os.getenv('GITHUB_CLIENT_ID'))
    data = dict(oauthClients = dict(github=github))

    if email is not None:
        u = db.query(User).filter(User.email == email).first()
        if u:
            has_password = u.password is not None
            data['user'] = dict(email=email, admin=u.is_admin, has_password=has_password)
    return data

