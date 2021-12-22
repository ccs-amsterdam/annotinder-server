from base64 import b64encode

import json

from amcat4annotator import auth
from amcat4annotator.db import CodingJob, get_units, set_annotation, Annotation
from tests.conftest import get_json, post_json, UNITS, CODEBOOK, RULES


def test_get_token(client, user):
    assert client.get('/token').status_code == 401
    auth.change_password(user, 'geheim')
    credentials = b64encode(f"{user.email}:geheim".encode('ascii')).decode('ascii')
    headers = {"Authorization": f"Basic {credentials}"}
    result = get_json(client, '/token', headers=headers)
    assert auth.verify_token(result['token']) == user


def test_get_token_admin(client, user, admin_user):
    assert get_json(client, '/token', user=user, query_string=dict(user='new@example.com'), expected=401)
    result = get_json(client, '/token', user=admin_user, query_string=dict(user=user.email), expected=200)
    assert auth.verify_token(result['token']) == user
    assert get_json(client, '/token', user=admin_user, query_string=dict(user='new@example.com'), expected=404)
    result = get_json(client, '/token', user=admin_user, query_string=dict(user="new@example.com", create="true"), expected=200)
    assert auth.verify_token(result['token']).email == "new@example.com"


def test_post_job(client, admin_user):
    job_dict = dict(title="test", codebook=CODEBOOK, rules=RULES, units=UNITS)
    jobid = post_json(client, '/codingjob', data=job_dict, user=admin_user)['id']
    job = CodingJob.get_by_id(jobid)
    assert job.title == "test"
    assert job.rules == RULES
    units = get_units(job.id)
    assert len(units) == 2
    assert {json.dumps(x.gold) for x in units} == {json.dumps(x.get('gold')) for x in UNITS}


def test_get_job(client, admin_user, job):
    j = get_json(client, f'/codingjob/{job}', user=admin_user)
    assert j['rules'] == RULES
    assert len(j['units']) == 2
    assert {x['unit']['text'] for x in j['units']} == {x['unit']['text'] for x in UNITS}
    assert {x['unit'].get('gold') for x in j['units']} == {x['unit'].get('gold') for x in UNITS}


def test_job_admin_required(client, user):
    post_json(client, '/codingjob', data={}, user=user, expected=401)


def test_get_codebook(client, user, job):
    cb = get_json(client, f'/codingjob/{job}/codebook', user=user)
    assert cb == CODEBOOK


def test_get_next_unit(client, user, job):
    unit = get_json(client, f'/codingjob/{job}/unit', user=user)
    assert unit['unit']['text'] in {"unit1", "unit2"}


def test_seek_unit(client, user, job):
    units = list(get_units(job))
    set_annotation(units[1].id, user.email, {"answer": 42})
    set_annotation(units[0].id, user.email, {})
    unit = get_json(client, f'/codingjob/{job}/unit', user=user, query_string=dict(index=0))
    assert unit['id'] == units[1].id
    assert unit.get('annotation') == {"answer": 42}


def test_set_annotation(client, user, job):
    units = list(get_units(job))
    unit = units[0].id
    post_json(client, f'/codingjob/{job}/unit/{unit}/annotation', user=user, data={"foo": "bar"}, expected=204, decode=False)
    a = list(Annotation.select().where(Annotation.coder==user.id, Annotation.unit==units[0].id))
    assert len(a) == 1
    assert a[0].annotation == {"foo": "bar"}


def test_progress(client, user, job):
    p = get_json(client,  f'/codingjob/{job}/progress', user=user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 0
    units = list(get_units(job))
    set_annotation(units[0].id, user.email, {})
    p = get_json(client,  f'/codingjob/{job}/progress', user=user)
    assert p['n_coded'] == 1

