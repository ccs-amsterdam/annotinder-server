import pytest
from fastapi.testclient import TestClient

import amcat4annotator
from amcat4annotator import auth, api
from amcat4annotator.db import User, create_codingjob, add_jobsets, CodingJob


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
    u = User.create(email="user@example.com")
    yield u
    User.delete_by_id(u.id)


@pytest.fixture()
def admin_user():
    u = User.create(email="admin@example.com", is_admin=True)
    yield u
    User.delete_by_id(u.id)


@pytest.fixture()
def password_user():
    u = User.create(email="batman@example.com", password="secret")
    yield u
    User.delete_by_id(u.id)


@pytest.fixture()
def job():
    u = User.create(email="robin@example.com", password="secret", is_admin=True)
    job = create_codingjob(title="test", codebook=CODEBOOK, jobsets=None, provenance=PROVENANCE, units=UNITS, rules=RULES, creator=u)

    yield job
    CodingJob.delete_by_id(job)
    User.delete_by_id(u.id)



@pytest.fixture()
def app():
    return amcat4annotator.app


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

