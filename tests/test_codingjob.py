import pytest

from amcat4annotator.db import create_codingjob, get_units, CodingJob, User, set_annotation, Annotation, get_next_unit

UNITS = [{"unit": {"text": "unit1"}},
         {"unit": {"text": "unit2"}}]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}
RULES = {"ruleset": "crowdcoding"}

@pytest.fixture()
def job():
    job = create_codingjob(title="test", codebook=CODEBOOK, provenance=PROVENANCE, units=UNITS, rules=RULES).id
    yield job
    CodingJob.delete_by_id(job)


def test_codingjob(job: int):
    job2 = CodingJob.get_by_id(job)
    assert job2.codebook['foo'] == 'bar'


def test_get_units(job: int):
    retrieved_units = list(get_units(job))
    print(retrieved_units[0].unit)
    assert len(UNITS) == len(retrieved_units)
    assert {u['unit']['text'] for u in UNITS} == {u.unit['text'] for u in retrieved_units}


def test_annotate(job: int):
    unit = get_units(job)[0]

    #TODO Create methods for creating user, retrieving annotations?
    c = User.create(email="a@b.c")
    a = set_annotation(unit.id, c.email, {"foo": "bar"})
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'bar'
    a2 = set_annotation(unit.id, c.email, {"foo": "baz"})
    assert a.id == a2.id
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'baz'


def test_get_next_unit(job: int):
    c = User.create(email="a@b.c")
    u = get_next_unit(job, c.email)
    assert u.unit['text'] in {"unit1", "unit2"}
    set_annotation(u.id, c.email, {})
    u2 = get_next_unit(job, c.email)
    assert {u.unit['text'], u2.unit['text']} == {"unit1", "unit2"}
    set_annotation(u2.id, c.email, {})
    u3 = get_next_unit(job, c.email)
    assert u3 is None


