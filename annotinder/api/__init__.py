"""
Annotinder Annotator Module API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from annotinder.api.users import app_annotator_users
from annotinder.api.codingjob import app_annotator_codingjob
from annotinder.api.guest import app_annotator_guest


app = FastAPI(
  title="annotinder",
  description=__doc__,
  openapi_tags=[
    dict(name="annotator users", description="Endpoints for user management"),
    dict(name="annotator codingjob", description="Endpoints for creating and managing codingjobs, and the core process of getting units and posting annotations"),
    dict(name="annotator guest", description="Endpoints for unregistered guests"),
  ]
)

app.include_router(app_annotator_users)
app.include_router(app_annotator_codingjob)
app.include_router(app_annotator_guest)

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
