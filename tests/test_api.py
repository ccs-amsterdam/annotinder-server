from base64 import b64encode

import json

from amcat4annotator import auth
from amcat4annotator.db import CodingJob, get_units, get_jobset, get_jobset_units, set_annotation, Annotation
from tests.conftest import get_json, post_json, UNITS, CODEBOOK, RULES


def test_get_token(client, user):
    cred = dict(username=user.email, password='geheim')
    assert client.post('annotator/users/me/token', data=cred).status_code == 401
    auth.change_password(user, 'geheim')
    result = post_json(client, 'annotator/users/me/token', data=cred, expected=200)
    assert auth.verify_token(result['token']) == user


def test_get_token_admin(client, user, admin_user):
    get_json(client, 'annotator/users/new@example.com/token', user=user, params=dict(username=user.email), expected=401)
    result = get_json(client, f'annotator/users/{user.email}/token', user=admin_user, params=dict(user=user.email), expected=200)
    assert auth.verify_token(result['token']) == user
    get_json(client, f'annotator/users/new@example.com/token', user=admin_user, params=dict(username='new@example.com'), expected=404)


def test_post_job(client, admin_user):
    job_dict = dict(title="test", codebook=CODEBOOK, rules=RULES, units=UNITS)
    jobid = post_json(client, 'annotator/codingjob', json=job_dict, user=admin_user)['id']
    job = CodingJob.get_by_id(jobid)
    assert job.title == "test"
    assert job.rules == RULES
    units = get_units(job.id)
    assert len(units) == 2
    assert {json.dumps(x.gold) for x in units} == {json.dumps(x.get('gold')) for x in UNITS}


def test_get_job(client, admin_user, job):
    j = get_json(client, f'annotator/codingjob/{job.id}', user=admin_user)
    assert j['rules'] == RULES
    assert len(j['units']) == 2
    assert {x['unit']['text'] for x in j['units']} == {x['unit']['text'] for x in UNITS}
    assert {x['unit'].get('gold') for x in j['units']} == {x['unit'].get('gold') for x in UNITS}


def test_job_admin_required(client, user):
    post_json(client, 'annotator/codingjob', data={}, user=user, expected=401)


def test_get_codebook(client, user, job):
    cb = get_json(client, f'annotator/codingjob/{job.id}/codebook', user=user)
    assert cb == CODEBOOK


def test_get_next_unit(client, user, job):
    unit = get_json(client, f'annotator/codingjob/{job.id}/unit', user=user)
    assert unit['unit']['text'] in {"unit1", "unit2"}


def test_seek_unit(client, user, job):
    jobset = get_jobset(job.id, user.id, True)
    units = get_jobset_units(jobset)
    set_annotation(units[1], user, {"answer": 42})
    set_annotation(units[0], user, {})
    unit = get_json(client, f'annotator/codingjob/{job.id}/unit', user=user, params=dict(index=0))
    assert unit['id'] == units[1].id
    assert unit.get('annotation') == {"answer": 42}


def test_set_annotation(client, user, job):
    jobset = get_jobset(job.id, user.id, True)
    units = get_jobset_units(jobset)
    unit = units[0]
    post_json(client, f'annotator/codingjob/{job.id}/unit/{unit.id}/annotation', user=user, expected=204, 
              json={"annotation": [{"foo": "bar"}]})
    a = list(Annotation.select().where(Annotation.coder==user.id, Annotation.unit==units[0].id))
    assert len(a) == 1
    assert a[0].annotation == [{"foo": "bar"}]
    assert a[0].status == "DONE"
    post_json(client, f'annotator/codingjob/{job.id}/unit/{unit.id}/annotation', user=user, expected=204, 
              json={"status": "IN_PROGRESS", "annotation": [{"foo": "baz"}]})
    a = list(Annotation.select().where(Annotation.coder == user.id, Annotation.unit == units[0].id))
    assert len(a) == 1
    assert a[0].annotation == [{"foo": "baz"}]
    assert a[0].status == "IN_PROGRESS"


def test_progress(client, user, job):
    p = get_json(client,  f'annotator/codingjob/{job.id}/progress', user=user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 0
    jobset = get_jobset(job.id, user.id, True)
    units = get_jobset_units(jobset)
    set_annotation(units[0], user, {})
    p = get_json(client,  f'annotator/codingjob/{job.id}/progress', user=user)
    assert p['n_coded'] == 1


def test_job_users(client, admin_user, user):
    job_dict = dict(title="test", codebook=CODEBOOK, units=UNITS, rules=RULES)
    # user should be able to code a non-restricted job
    jobid = post_json(client, 'annotator/codingjob', json={'authorization': {'restricted': False}, **job_dict}, user=admin_user)['id']
    get_json(client, f'annotator/codingjob/{jobid}/unit', user=user, expected=200)
    # Which should be the default
    jobid = post_json(client, 'annotator/codingjob', json={**job_dict}, user=admin_user)['id']
    get_json(client, f'annotator/codingjob/{jobid}/unit', user=user, expected=200)
    # user should not be able to code a restricted job
    jobid = post_json(client, 'annotator/codingjob', json={'authorization': {'restricted': True}, **job_dict}, user=admin_user)['id']
    get_json(client, f'annotator/codingjob/{jobid}/unit', user=user, expected=401)
    # Add a user to the job
    post_json(client, f'annotator/codingjob/{jobid}/users', json={'users': [user.email]}, user=admin_user, expected=204)
    get_json(client, f'annotator/codingjob/{jobid}/unit', user=user, expected=200)
    # Can we add users as part of the rules?
    jobid = post_json(client, 'annotator/codingjob', user=admin_user,
                      json={'authorization': {'restricted': True, 'users': [user.email]}, **job_dict})['id']
    get_json(client, f'annotator/codingjob/{jobid}/unit', user=user, expected=200)


def test_job_tokens(client, job, admin_user):
    t = get_json(client, f'annotator/codingjob/{job}/token', user=admin_user)
    assert set(get_json(client, f'annotator/guest/jobtoken', params=dict(token=t['token'])).keys()) == {"job_id", "email", "token", "is_admin"}
    result = get_json(client, f'annotator/guest/jobtoken', params=dict(token=t['token'], user_id='pietje'))
    assert 'pietje' in result['email']
