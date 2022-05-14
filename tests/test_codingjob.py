import pytest

from amcat4annotator.models import CodingJob, User, Annotation

from tests.conftest import UNITS


def test_codingjob(job: int):
    job2 = CodingJob.get_by_id(job)
    assert job2.jobsets[0].codebook['foo'] == 'bar'


def test_get_units(job: int):
    retrieved_units = list(get_units(job))
    assert len(UNITS) == len(retrieved_units)
    assert {u['unit']['text'] for u in UNITS} == {u.unit['text'] for u in retrieved_units}


def test_annotate(job: int, user: User):
    jobset = get_jobset(job.id, user.id, True)
    units = get_jobset_units(jobset)
    unit = units[0]
    a = set_annotation(unit, user, {"foo": "bar"})
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'bar'
    assert Annotation.get_by_id(a.id).status == "DONE"
    a2 = set_annotation(unit, user, {"foo": "baz"}, status="IN_PROGRESS")
    assert a.id == a2.id
    assert Annotation.get_by_id(a.id).annotation['foo'] == 'baz'
    assert Annotation.get_by_id(a.id).status == "IN_PROGRESS"
