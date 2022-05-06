"""
AmCAT4 Annotator Module API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amcat4annotator.api.users import app_annotator_users
from amcat4annotator.api.codingjob import app_annotator_codingjob
from amcat4annotator.api.guest import app_annotator_guest


app = FastAPI(
  title="AmCAT4Annotator",
  description=__doc__,
  openapi_tags=[
    dict(name="annotator users", description="Endpoints for user management"),
    dict(name="annotator codingjob", description="Endpoints for creating and managing codingjobs, and the core process of getting units and posting annotations"),
    dict(name="annotator guest", description="Endpoints for unregistered guests"),
  ]
)

app.include_router(app_annotator_users, prefix='/annotator')
app.include_router(app_annotator_codingjob, prefix='/annotator')
app.include_router(app_annotator_guest, prefix='/annotator')

app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)
