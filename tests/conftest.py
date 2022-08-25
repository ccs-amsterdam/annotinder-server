import pytest
from fastapi.testclient import TestClient

import annotinder
from annotinder import auth, api
from annotinder.database import get_test_db
from annotinder.crud import crud_codingjob, crud_user

UNITS = [{"id": 1, "unit": {"text": "unit1"}},
         {"id": 2, "unit": {"text": "unit2"}, "gold": {"element": "au"}}]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}
RULES = {"ruleset": "crowdcoding"}

@pytest.fixture()
def client():
    return TestClient(api.app)

@pytest.fixture()
def user():
    with get_test_db() as db:
        u = crud_user.create_user(username = "user@example.com")
        db.commit()
        db.refresh(u)
        yield u
        db.delete(u)
        db.commit()


@pytest.fixture()
def admin_user():
    with get_test_db() as db:
        u = crud_user.create_user(username = "admin@example.com", admin=True)
        db.commit()
        db.refresh(u)
        yield u
        db.delete(u)
        db.commit()


@pytest.fixture()
def password_user():
    with get_test_db() as db:
        u = crud_user.create_user(email="batman@example.com", password="secret")
        db.commit()
        db.refresh(u)
        yield u
        db.delete(u)
        db.commit()


@pytest.fixture()
def job():
    with get_test_db() as db:
        u = crud_user.create_user(email="robin@example.com", password="secret", is_admin=True)
        db.commit()
        db.refresh(u)
        job = crud_codingjob.create_codingjob(title="test", codebook=CODEBOOK, jobsets=None, provenance=PROVENANCE, units=UNITS, rules=RULES, creator=u)
        db.commit()
        db.refresh(job)
        yield job
        db.delete(u)
        db.delete(job)
        db.commit()


@pytest.fixture()
def app():
    return annotinder.app


def build_headers(user=None, headers=None, password=None):
    if not headers:
        headers = {}
    if user and password:
        raise Exception("Sorry! We don't do that here")
    elif user:
        headers['Authorization'] = f"Bearer {auth.get_token(user)}"
    return headers


def get_json(client: TestClient, url, expected=200, headers=None, user=None, **kargs):
    """Get the given URL. If expected is 2xx, return the result as parsed json"""
    response = client.get(url, headers=build_headers(user, headers), **kargs)
    assert response.status_code == expected, \
        f"GET {url} returned {response.status_code}, expected {expected}, {response.json()}"
    if expected // 100 == 2:
        return response.json()


def post_json(client: TestClient, url, expected=201, headers=None, user=None, **kargs):
    response = client.post(url, headers=build_headers(user, headers), **kargs)
    assert response.status_code == expected, f"POST {url} returned {response.status_code}, expected {expected}\n" \
                                             f"{response.json()}"
    if not expected == 204:
        return response.json()

