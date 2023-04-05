import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.orm import sessionmaker, Session

from annotinder.api import app
from annotinder.database import Base, get_db
from annotinder.crud import crud_user
from annotinder.auth import get_token

import os
from dotenv import load_dotenv
load_dotenv()
DB_HOST = os.getenv('POSTGRES_HOST')
DB_NAME = os.getenv('POSTGRES_NAME') 
DB_PW = os.getenv('POSTGRES_PASSWORD') 

DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(
  DATABASE_URL, connect_args={}
)

if not database_exists(engine.url):
    create_database(engine.url)
else:
    engine.connect()

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestSessionLocal()
    try:
        print('open test db')
        yield db
    finally:
        print('close test db')
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

@pytest.fixture(scope='session', autouse=True)
def db():
    Base.metadata.create_all(bind=engine)
    yield TestSessionLocal()
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope='session')
def coders(db):
    coders = []
    for i in range(0,3):
        email = f"coder_{i}@test.com"
        u = crud_user.register_user(db, username=email, email=email, 
                                    password='supersecret', admin=False)
        headers = {"Authorization": f"Bearer {get_token(u)}"}
        coders.append(dict(headers = headers, user=u, password='testpassword'))
    return coders
    
@pytest.fixture(scope='session')
def admin(db):
    u = crud_user.register_user(db, username="Admin user", 
                                email='admin@test.com', password='supersecret', admin=True)
    headers = {"Authorization": f"Bearer {get_token(u)}"}
    return dict(headers = headers, user=u, password='testpassword') 

