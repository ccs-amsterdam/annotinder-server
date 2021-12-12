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
        [{'codingjob': job, 'unit': u['unit']} for u in units]
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


class User(Model):
    id = AutoField()
    email = CharField(max_length=512)
    #TODO add password and auth
    class Meta:
        database = db


class Annotation(Model):
    id = AutoField()
    unit = ForeignKeyField(Unit)
    coder = ForeignKeyField(User)
    annotation = JSONField()
    #TODO add status
    class Meta:
        database = db


def get_units(codingjob_id: int) -> Iterable[Unit]:
    return Unit.select().where(Unit.codingjob == codingjob_id)


def set_annotation(unit_id: int, coder: str, annotation: dict) -> Annotation:
    """Create a new annotation or replace an existing annotation"""
    c = User.get(User.email == coder)
    try:
        ann = Annotation.get(unit=unit_id, coder=c.id)
    except Annotation.DoesNotExist:
        return Annotation.create(unit=unit_id, coder=c.id, annotation=annotation)
    else:
        ann.annotation = annotation
        ann.save()
        return ann



def get_next_unit(codingjob_id: int, coder: str) -> Optional[Unit]:
    """Return the next unit to code, or None if coder is done"""
    #TODO: implement rules / logic
    c = User.get(User.email == coder)
    coded = {t[0] for t in Annotation.select(Unit.id).join(Unit).
        filter(Unit.codingjob == codingjob_id,
               Annotation.coder == c.id).tuples()}
    units = list(Unit.select().where(Unit.codingjob == codingjob_id,
                        Unit.id.not_in(coded)).limit(1).execute())
    if units:
        return units[0]






def initialize_if_needed():
    db.create_tables([CodingJob, Unit, Annotation, User])
