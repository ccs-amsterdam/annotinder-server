import os
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, status
from fastapi.params import Query, Depends
from sqlalchemy.orm import Session
from annotinder.database import engine, get_db

load_dotenv()


app_annotator_host = APIRouter(prefix='/host', tags=["annotator host"])

@app_annotator_host.get("")
def get_host_info(db: Session = Depends(get_db)):
    """
    Get information about a host server. In particular, get any oauth clients that can be used to authentiate the user
    """
    github = dict(client_id = os.getenv('GITHUB_CLIENT_ID'))

    return dict(oauthClients = dict(github=github))
