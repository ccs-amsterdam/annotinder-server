import json

import pytest

import amcat4annotator
from amcat4annotator import auth
from amcat4annotator.db import User, create_codingjob, CodingJob

UNITS = [{"unit": {"text": "unit1"}},
         {"unit": {"text": "unit2"}, "gold": {"element": "au"}}]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}
RULES = {"ruleset": "crowdcoding"}


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
    # TODO: no idea why create_codingjob yields an int - probably should standardize and refactor all db functions
    #       into a separate module and use only model objects
    job = create_codingjob(title="test", codebook=CODEBOOK, provenance=PROVENANCE, units=UNITS, rules=RULES).id
    yield job
    CodingJob.delete_by_id(job)


@pytest.fixture()
def app():
    return amcat4annotator.app


def _build_headers(headers=None, user=None):
    if not headers:
        headers = {}
    if user:
        headers['Authorization'] = f"Bearer {auth.get_token(user)}"
    return headers


def get_json(client, url, expected=200, headers=None, user=None, **kargs):
    headers = _build_headers(headers, user)
    response = client.get(url, headers=headers, **kargs)
    assert response.status_code == expected
    return json.loads(response.get_data(as_text=True))


def post_json(client, url, data, expected=201, user=None, headers=None, content_type='application/json', decode=True,
              **kargs):
    headers = _build_headers(headers, user)
    response = client.post(url, data=json.dumps(data), headers=headers, content_type=content_type, **kargs)
    assert response.status_code == expected
    if decode:
        return json.loads(response.get_data(as_text=True))
