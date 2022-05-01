import pytest

from amcat4annotator.db import User, set_annotation, CodingJob, get_units
from amcat4annotator.rules import get_next_unit, get_ruleset, get_progress_report, seek_unit


def test_crowdcoding_next(job: int, user: User):
    """
    Do we get the next uncoded unit for a crowd coder?
    """
    job = CodingJob.get_by_id(job)
    u, index = get_next_unit(job, user)
    assert u.unit['text'] in {"unit1", "unit2"}
    set_annotation(u.id, user.email, {})
    u2, index = get_next_unit(job, user)
    assert {u.unit['text'], u2.unit['text']} == {"unit1", "unit2"}
    set_annotation(u2.id, user.email, {})
    u3, index = get_next_unit(job, user)
    assert u3 is None


def test_crowdcoding_next_leastcoded(job: int, user: User, admin_user: User, password_user: User):
    """Does crowdcoding favour units with fewer anotations?"""
    job = CodingJob.get_by_id(job)
    units = list(get_units(job.id))
    set_annotation(units[0].id, admin_user.email, {})
    u, index = get_next_unit(job, user)
    assert u == units[1]
    set_annotation(units[0].id, password_user.email, {})
    set_annotation(units[1].id, password_user.email, {})
    u, index = get_next_unit(job, user)
    assert u == units[1]


def test_progress(job: int, user: User):
    job = CodingJob.get_by_id(job)
    p = get_progress_report(job, user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 0
    units = list(get_units(job.id))
    set_annotation(units[0].id, user.email, {})
    p = get_progress_report(job, user)
    assert p['n_total'] == 2
    assert p['n_coded'] == 1


def test_seek_backwards(job: int, user: User):
    """Can we retrieve the first coded unit?"""
    job = CodingJob.get_by_id(job)
    units = list(get_units(job.id))
    assert seek_unit(job, user, index=0) == None
    set_annotation(units[1].id, user.email, {})
    set_annotation(units[0].id, user.email, {})
    assert seek_unit(job, user, index=0).id == units[1].id
