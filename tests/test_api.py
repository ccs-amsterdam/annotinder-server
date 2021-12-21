from base64 import b64encode

import json

from amcat4annotator import auth
from amcat4annotator.db import CodingJob, get_units
from tests.conftest import get_json, post_json, UNITS, CODEBOOK, RULES


def test_get_token(client, user):
    assert client.get('/token').status_code == 401
    auth.change_password(user, 'geheim')
    credentials = b64encode(f"{user.email}:geheim".encode('ascii')).decode('ascii')
    headers = {"Authorization": f"Basic {credentials}"}
    result = get_json(client, '/token', headers=headers)
    assert auth.verify_token(result['token']) == user


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