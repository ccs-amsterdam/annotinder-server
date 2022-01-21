import json
import os
import sys
import datetime
from enum import Enum
from typing import List, Iterable, Optional

from peewee import DateTimeField, Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, DoesNotExist, \
    BooleanField, fn
import logging


STATUS = Enum('Status', ['NOT_STARTED', 'IN_PROGRESS', 'DONE', 'SKIPPED'])

db_name = os.environ.get("ANNOTATOR_DB_NAME")
if not db_name:
    print(f"Note: Using database {db_name}, user ANNOTATOR_DB_NAME to change", file=sys.stderr)
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
        [{'codingjob': job, 'unit': u['unit'], 'gold': u.get('gold')} for u in units]
    ).execute()
    return job


class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE')
    unit = JSONField()
    gold = JSONField(null=True)

    class Meta:
        database = db


class User(Model):
    id = AutoField()
    email = CharField(max_length=512)
    is_admin = BooleanField(default=False)
    password = CharField(max_length=512, null=True)

    class Meta:
        database = db


class Annotation(Model):
    id = AutoField()
    unit = ForeignKeyField(Unit, on_delete='CASCADE')
    coder = ForeignKeyField(User, on_delete='CASCADE')
    status = CharField(max_length=64, default=STATUS.DONE.name)
    modified = DateTimeField(default=datetime.datetime.now())
    annotation = JSONField()

    class Meta:
        database = db


def get_units(codingjob_id: int) -> Iterable[Unit]:
    return Unit.select().where(Unit.codingjob == codingjob_id)

def get_user_jobs(user_id: int) -> list:
    """
    Retrieve all (active?) jobs
    """
    jobs = list(CodingJob.select())

    jobs_with_progress = []
    for job in jobs:
        data = {"id": job.id, "title": job.title}
        data["n_total"] = Unit.select().where(Unit.codingjob == job.id).count()

        annotations = Annotation.select().join(Unit).where(Unit.codingjob == job.id, Annotation.coder == user_id, Annotation.status != 'IN_PROGRESS')
        data["n_coded"] = annotations.count()
        data["modified"] = annotations.select(fn.MAX(Annotation.modified)).scalar() or 'NEW'
        jobs_with_progress.append(data)


    now = datetime.datetime.now()
    jobs_with_progress.sort(key=lambda x: now if x.get('modified') == 'NEW' else x.get('modified'), reverse=True)
    return jobs_with_progress


def set_annotation(unit_id: int, coder: str, annotation: dict, status: Optional[str] = None) -> Annotation:
    """Create a new annotation or replace an existing annotation"""
    c = User.get(User.email == coder)
    if status:
        status = status.upper()
        assert hasattr(STATUS, status)
    else:
        status = STATUS.DONE.name
    try:
        ann = Annotation.get(unit=unit_id, coder=c.id)
    except Annotation.DoesNotExist:
        return Annotation.create(unit=unit_id, coder=c.id, annotation=annotation, status=status)
    else:
        ann.annotation = annotation
        ann.status = status
        ann.modified = datetime.datetime.now()
        ann.save()
        return ann

#TODO: is it good practice to always call this on import?
db.create_tables([CodingJob, Unit, Annotation, User])
