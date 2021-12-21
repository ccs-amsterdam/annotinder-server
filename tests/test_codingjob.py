import pytest

from amcat4annotator.db import create_codingjob, get_units, CodingJob, User, set_annotation, Annotation, get_next_unit

from tests.conftest import UNITS

def test_codingjob(job: int):
    job2 = CodingJob.get_by_id(job)
    assert job2.codebook['foo'] == 'bar'


def test_get_units(job: int):
    retrieved_units = list(get_units(job))
    assert len(UNITS) == len(retrieved_units)
    assert {u['unit']['text'] for u in UNITS} == {u.unit['text'] for u in retrieved_units}


def test_annotate(job: int, user: User):
    unit = get_units(job)[0]
    #TODO Create methods for retrieving annotations?
    a = set_annotation(unit.id, user.email, {"foo": "bar"})
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'bar'
    a2 = set_annotation(unit.id, user.email, {"foo": "baz"})
    assert a.id == a2.id
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'baz'


def test_get_next_unit(job: int, user: User):
    u = get_next_unit(job, user.email)
    assert u.unit['text'] in {"unit1", "unit2"}
    set_annotation(u.id, user.email, {})
    u2 = get_next_unit(job, user.email)
    assert {u.unit['text'], u2.unit['text']} == {"unit1", "unit2"}
    set_annotation(u2.id, user.email, {})
    u3 = get_next_unit(job, user.email)
    assert u3 is None


