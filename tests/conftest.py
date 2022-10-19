import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from annotinder.api import app
from annotinder.database import Base, get_db
from annotinder.crud import crud_user
from annotinder.auth import get_token

SQLALCHEMY_TESTDB_URL = 'sqlite:///./test.db'

engine = create_engine(
  SQLALCHEMY_TESTDB_URL, connect_args={"check_same_thread": False}
)

TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

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
    

client = TestClient(app)