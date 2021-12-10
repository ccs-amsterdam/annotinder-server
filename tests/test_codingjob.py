from nose.tools import assert_true, assert_equal

from amcat4annotator.db import create_codingjob, get_units, get_codingjob


def test_post_codingjob():
    units = [{"unit": {"text": "unit1"}},
             {"unit": {"text": "unit2"}}]
    codebook = {"foo": "bar"}
    provenance = {"bar": "foo"}

    id = create_codingjob(codebook, provenance, units).id
    job = get_codingjob(id)
    assert_equal(job.codebook['foo'],  'bar')

    retrieved_units = list(get_units(id))
    assert_equal(len(units), len(retrieved_units))


def test_get_codingjobs_dne():
    assert_equal(get_codingjob(-1), None)
