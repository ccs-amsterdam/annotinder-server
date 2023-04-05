from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from dotenv import load_dotenv
load_dotenv()

## railway injects its own DB URL
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL is None:
  DB_HOST = os.getenv('POSTGRES_HOST')
  DB_NAME = os.getenv('POSTGRES_NAME') 
  DB_PW = os.getenv('POSTGRES_PASSWORD')
  DATABASE_URL = f"postgresql://{DB_NAME}:{DB_PW}@{DB_HOST}/annotinder"

engine = create_engine(
  DATABASE_URL, connect_args={}
)

if not database_exists(engine.url):
    create_database(engine.url)
else:
    # Connect the database if exists.
    engine.connect()


Base = declarative_base()
Base.metadata.create_all(bind=engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()
