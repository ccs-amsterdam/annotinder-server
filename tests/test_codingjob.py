from nose.tools import assert_true, assert_equal, assert_in, assert_is_none

from amcat4annotator.db import create_codingjob, get_units, get_codingjob, User, set_annotation, Annotation, \
    get_next_unit

UNITS = [{"unit": {"text": "unit1"}},
         {"unit": {"text": "unit2"}}]
CODEBOOK = {"foo": "bar"}
PROVENANCE = {"bar": "foo"}


def _create_codingjob():
    return create_codingjob(CODEBOOK, PROVENANCE, UNITS).id


def test_post_get_codingjob():
    id = _create_codingjob()
    job = get_codingjob(id)
    assert_equal(job.codebook['foo'],  'bar')


def test_get_units():
    id = _create_codingjob()
    retrieved_units = list(get_units(id))
    print(retrieved_units[0].unit)
    assert_equal(len(UNITS), len(retrieved_units))
    assert_equal({u['unit']['text'] for u in UNITS},
                 {u.unit['text'] for u in retrieved_units})


def test_annotate():
    id = _create_codingjob()
    unit = get_units(id)[0]

    #TODO Create methods for creating user, retrieving annotations?
    c = User.create(email="a@b.c")
    a = set_annotation(unit.id, c.email, {"foo": "bar"})
    assert_equal(Annotation.get_by_id(a.id).annotation['foo'], 'bar')
    a2 = set_annotation(unit.id, c.email, {"foo": "baz"})
    assert_equal(a.id, a2.id)
    assert_equal(Annotation.get_by_id(a.id).annotation['foo'], 'baz')


def test_get_next_unit():
    id = _create_codingjob()
    c = User.create(email="a@b.c")
    u = get_next_unit(id, c.email)
    assert_in(u.unit['text'], {"unit1", "unit2"})
    set_annotation(u.id, c.email, {})
    u2 = get_next_unit(id, c.email)
    assert_equal({u.unit['text'], u2.unit['text']},
                 {"unit1", "unit2"})
    set_annotation(u2.id, c.email, {})
    u3 = get_next_unit(id, c.email)
    assert_is_none(u3)


def test_get_codingjobs_dne():
    assert_equal(get_codingjob(-1), None)
