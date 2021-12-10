import json
import sys
from typing import List, Iterable, Optional

from peewee import Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, DoesNotExist
import logging

# IF we're running nose tests, we want an in-memory db
if 'nose' in sys.modules.keys():
    logging.warning("I think you're unit testing: using in-memory db")
    db = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
else:
    db = SqliteDatabase('amcat4annotator.db', pragmas={'foreign_keys': 1})

class JSONField(TextField):
    def db_value(self, value):
        return json.dumps(value)

    def python_value(self, value):
        if value is not None:
            return json.loads(value)


class CodingJob(Model):
    id = AutoField()
    codebook = JSONField()
    provenance = JSONField()

    class Meta:
        database = db


def create_codingjob(codebook: dict, provenance: dict, units: List[dict]) -> CodingJob:
    job = CodingJob.create(codebook=codebook, provenance=provenance)
    Unit.insert_many(
        [{'codingjob': job, 'unit': u} for u in units]
    ).execute()
    return job


def get_codingjob(codingjob_id: int) -> Optional[CodingJob]:
    try:
        return CodingJob.get_by_id(codingjob_id)
    except DoesNotExist:
        return None


class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob)
    unit = JSONField()

    class Meta:
        database = db


def get_units(codingjob_id: int) -> Iterable[Unit]:
    return Unit.select().where(Unit.codingjob == codingjob_id)



def initialize_if_needed():
    db.create_tables([CodingJob, Unit])
