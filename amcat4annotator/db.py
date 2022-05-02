import json
import os
import sys
import datetime
from enum import Enum
from typing import List, Iterable, Optional, Any

from peewee import DateTimeField, Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, DoesNotExist, \
    BooleanField, fn, JOIN

STATUS = Enum('Status', ['NOT_STARTED', 'IN_PROGRESS', 'DONE', 'SKIPPED'])

db_name = os.environ.get("ANNOTATOR_DB_NAME", "annotator.db")
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

class User(Model):
    id = AutoField()
    email = CharField(max_length=512)
    is_admin = BooleanField(default=False)
    restricted_job = IntegerField(default=None, null=True)
    password = CharField(max_length=512, null=True)

    class Meta:
        database = db

class CodingJob(Model):
    id = AutoField()
    title = CharField()
    codebook = JSONField()
    provenance = JSONField()
    rules = JSONField()
    creator = ForeignKeyField(User, on_delete='CASCADE')
    restricted = BooleanField(default=False)
    created = DateTimeField(default=datetime.datetime.now())
    archived = BooleanField(default=False)

    class Meta:
        database = db


def create_codingjob(title: str, codebook: dict, provenance: dict, rules: dict, creator: User, units: List[dict],
                     authorization: Optional[dict]=None) -> int:
    if authorization is None:
        authorization = {}
    restricted = authorization.get('restricted', False)
    job = CodingJob.create(title=title, codebook=codebook, rules=rules, creator=creator, provenance=provenance, restricted=restricted)
    Unit.insert_many(
        [{'codingjob': job, 'external_id': u['id'], 'unit': u['unit'], 'gold': u.get('gold')} for u in units]
    ).execute()
    users = authorization.get('users', [])
    if users:
        set_jobusers(codingjob_id=job.id, emails=users)
    return job


class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE')
    external_id = CharField()  
    unit = JSONField()
    gold = JSONField(null=True)

    class Meta:
        database = db
        indexes = ((('codingjob', 'external_id'), True),)


class Annotation(Model):
    id = AutoField()
    unit = ForeignKeyField(Unit, on_delete='CASCADE')
    coder = ForeignKeyField(User, on_delete='CASCADE')
    status = CharField(max_length=64, default=STATUS.DONE.name)
    modified = DateTimeField(default=datetime.datetime.now())
    annotation = JSONField()

    class Meta:
        database = db


class JobUser(Model):
    user = ForeignKeyField(User, on_delete='CASCADE')
    job = ForeignKeyField(CodingJob, on_delete='CASCADE')
    is_owner = BooleanField(default=False)

    class Meta:
        database = db
        indexes = ((('user', 'job'), True),)

def get_jobusers(codingjob_id: int) -> Iterable[str]:
    jobusers = list(User.select(User.email).join(JobUser, JOIN.LEFT_OUTER).where(JobUser.job == codingjob_id))
    return [u.email for u in jobusers]

def set_jobusers(codingjob_id: int, emails: Iterable[str], only_add: bool = False) -> Iterable[str]:
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If only_add is True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    emails = set(emails)
    existing_emails = set(get_jobusers(codingjob_id))

    for email in emails:
        if email in existing_emails:
            continue
        user = User.get_or_none(User.email == email)
        if not user:
            user = User.create(email=email)
        JobUser.create(user=user, job_id=codingjob_id)

    if only_add:
        emails = emails.union(existing_emails)
    else:
        rm_emails = existing_emails - emails
        for rm_email in rm_emails:
            user = User.get_or_none(User.email == rm_email)
            JobUser.delete().where((JobUser.user==user) & (JobUser.job==codingjob_id)).execute()

    return list(emails)


def get_units(codingjob_id: int) -> Iterable[Unit]:
    return Unit.select().where(Unit.codingjob == codingjob_id)


def get_user_data():
    """
    Retrieve list of users (admin only)
    (at some point also add things like progress)
    """
    users = list(User.select())
    return [{"id": u.id, "is_admin": u.is_admin, "email": u.email} for u in users]


def get_jobs() -> list:
    """
    Retrieve all jobs. Only basic meta data. 
    """
    jobs = list(CodingJob.select())
    data = [dict(id= job.id, title= job.title, created= job.created, archived= job.archived, creator=job.creator.email) for job in jobs]
    data.sort(key=lambda x: x.get('created'), reverse=True)
    return data


def get_user_jobs(user: User) -> list:
    """
    Retrieve all user jobs, including progress
    """
    if user.restricted_job is not None:
        jobs = list(CodingJob.select().where(CodingJob.id == user.restricted_job))
    else:
        open_jobs = list(CodingJob.select().where(CodingJob.restricted == False))
        restricted_jobs = list(CodingJob.select().join(JobUser, JOIN.LEFT_OUTER).where((CodingJob.restricted == True) & (JobUser.user == user.id)))
        jobs = open_jobs + restricted_jobs

    jobs_with_progress = []
    for job in jobs:
        if job.archived: continue
        data = {"id": job.id, "title": job.title, "created": job.created, "creator": job.creator.email}
        
        if 'units_per_coder' in job.rules:
            data["n_total"] = job.rules['units_per_coder']
        else:
            data["n_total"] = Unit.select().where(Unit.codingjob == job.id).count()

        annotations = Annotation.select().join(Unit).where(Unit.codingjob == job.id, Annotation.coder == user.id, Annotation.status != 'IN_PROGRESS')
        data["n_coded"] = annotations.count()
        data["modified"] = annotations.select(fn.MAX(Annotation.modified)).scalar() or 'NEW'
        jobs_with_progress.append(data)

    jobs_with_progress.sort(key=lambda x: x.get('created') if x.get('modified') == 'NEW' else x.get('modified'), reverse=True)
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
db.create_tables([CodingJob, Unit, Annotation, User, JobUser])
