"""
Annotinder Annotator Module API
"""

import os
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from annotinder.api.host import app_annotator_host
from annotinder.api.users import app_annotator_users
from annotinder.api.codingjob import app_annotator_codingjob
from annotinder.api.guest import app_annotator_guest

load_dotenv()

## For invited users with user_id, name is [user_id]@invited


app = FastAPI(
  title="annotinder",
  description=__doc__,
  openapi_tags=[
    dict(name="annotator host", description="Endpoints for host server"),  
    dict(name="annotator users", description="Endpoints for user management"),
    dict(name="annotator codingjob", description="Endpoints for creating and managing codingjobs, and the core process of getting units and posting annotations"),
    dict(name="annotator guest", description="Endpoints for unregistered guests"),
  ]
)

@app.on_event("startup")
def startup_event():
  SECRET_KEY = os.getenv('SECRET_KEY') 
  if SECRET_KEY is None:
    raise NotImplementedError('A .env file with a SECRET_KEY needs to be created. You can run: "python -m annotinder create_env"')

app.include_router(app_annotator_host)
app.include_router(app_annotator_users)
app.include_router(app_annotator_codingjob)
app.include_router(app_annotator_guest)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=False,
  allow_methods=["*"],
  allow_headers=["*"],
)


