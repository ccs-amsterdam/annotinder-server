import json
import os
import sys
from enum import Enum
from typing import List, Iterable, Optional

from peewee import Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, DoesNotExist, \
    BooleanField
import logging

STATUS = Enum('Status', ['NOT_STARTED', 'IN_PROGRESS', 'DONE', 'SKIPPED'])

db_name = os.environ.get("ANNOTATOR_DB_NAME")
if not db_name:
    logging.info("Database not specified, using in-memory db. "
                 "Specify ANNOTATOR_DB_NAME environment variable if required")
    db_name = ":memory:"
db = SqliteDatabase(db_name, pragmas={'foreign_keys': 1})


class JSONField(TextField):
    def db_value(self, value):
        return json.dumps(value)

    def python_value(self, value):
        if value is not None:
            return json.loads(value)


class CodingJob(Model):
    id = AutoField()
    title = CharField()
    codebook = JSONField()
    provenance = JSONField()
    rules = JSONField()

    class Meta:
        database = db


def create_codingjob(title: str, codebook: dict, provenance: dict, rules: dict, units: List[dict]) -> int:
    job = CodingJob.create(title=title, codebook=codebook, rules=rules, provenance=provenance)
    Unit.insert_many(
        [{'codingjob': job, 'unit': u['unit']} for u in units]
    ).execute()
    return job

class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE')
    unit = JSONField()
    gold = BooleanField(default=False)
    status = CharField(max_length=64, default=STATUS.NOT_STARTED.name)

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
    unit = ForeignKeyField(Unit, on_delete='CASCADE')
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


#TODO: is it good practice to always call this on import?
db.create_tables([CodingJob, Unit, Annotation, User])
