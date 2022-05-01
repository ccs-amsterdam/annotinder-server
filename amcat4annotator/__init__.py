"""
AmCAT4 Annotator Module API
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amcat4annotator.api import app_annotator

app = FastAPI(
  title="AmCAT4Annotator",
  description=__doc__,
  openapi_tags=[
    dict(name="annotator", description="Endpoints for annotator")
  ]
)

app.include_router(app_annotator)
app.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

