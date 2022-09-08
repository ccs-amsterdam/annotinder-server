import pytest

from annotinder.models import User, CodingJob
from annotinder.unitserver import get_next_unit, get_ruleset, get_progress_report, seek_unit


def test_crowdcoding_next(job: int, user: User):
    """
    Do we get the next uncoded unit for a crowd coder?
    """
    job = CodingJob.get_by_id(job.id)
    u, index = get_next_unit(job, user)
    assert u.unit['text'] in {"unit1", "unit2"}
    set_annotation(u, user, {})
    u2, index = get_next_unit(job, user)
    assert {u.unit['text'], u2.unit['text']} == {"unit1", "unit2"}
    set_annotation(u2, user, {})
    u3, index = get_next_unit(job, user)
    assert u3 is None


def test_crowdcoding_next_leastcoded(job: int, user: User, admin_user: User, password_user: User):
    """Does crowdcoding favour units with fewer anotations?"""
    jobuser = get_jobuser(job.id, user.id, True)
    jobset = jobuser.jobset
    units = get_jobset_units(jobset)
    set_annotation(units[0], admin_user, {})
    u, index = get_next_unit(job, user)
    assert u == units[1]

    jobuser = get_jobuser(job.id, user.id, True)
    jobset = jobuser.jobset
    units = get_jobset_units(jobset)
    set_annotation(units[0], password_user, {})
    set_annotation(units[1], password_user, {})
    u, index = get_next_unit(job, user)
    assert u == units[1]


def test_progress(job: int, user: User):
    job = CodingJob.get_by_id(job)
    p = get_progress_report(job, user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 0

    jobuser = get_jobuser(job.id, user.id, True)
    jobset = jobuser.jobset
    units = get_jobset_units(jobset)
    set_annotation(units[0], user, {})
    p = get_progress_report(job, user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 1


def test_seek_backwards(job: int, user: User):
    """Can we retrieve the first coded unit?"""
    jobuser = get_jobuser(job.id, user.id, True)
    jobset = jobuser.jobset
    units = get_jobset_units(jobset)
    assert seek_unit(job, user, index=0) == None
    set_annotation(units[1], user, {})
    set_annotation(units[0], user, {})
    assert seek_unit(job, user, index=0).id == units[1].id
