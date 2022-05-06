import json
import os
import sys
import datetime
from enum import Enum
from typing import List, Iterable, Optional, Any

from peewee import DateTimeField, Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, \
    BooleanField, JOIN

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

class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE')
    external_id = CharField()  
    unit = JSONField()
    gold = JSONField(null=True)

    class Meta:
        database = db
        indexes = ((('codingjob', 'external_id'), True),)  # means that this combination should be unique


class Annotation(Model):
    id = AutoField()
    unit = ForeignKeyField(Unit, on_delete='CASCADE')
    coder = ForeignKeyField(User, on_delete='CASCADE')
    status = CharField(max_length=64, default=STATUS.DONE.name)
    modified = DateTimeField(default=datetime.datetime.now())
    annotation = JSONField()

    class Meta:
        database = db
        indexes = ((('unit', 'coder'), True),)

class JobUser(Model):
    user = ForeignKeyField(User, on_delete='CASCADE')
    job = ForeignKeyField(CodingJob, on_delete='CASCADE')
    can_code = BooleanField(default=True)
    can_edit = BooleanField(default=False)
    unit_set = CharField(max_length=512, default=None, null=True)
    unit_set_index = IntegerField(default=None, null=True)

    class Meta:
        database = db
        indexes = ((('user', 'job'), True),)



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
        set_job_coders(codingjob_id=job.id, emails=users)
    return job

def get_job_coders(codingjob_id: int) -> Iterable[str]:
    return list(User.select(User.email).join(JobUser, JOIN.LEFT_OUTER).where(JobUser.job == codingjob_id, JobUser.can_code == True))
    
def set_job_coders(codingjob_id: int, emails: Iterable[str], only_add: bool = False) -> Iterable[str]:
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If only_add is True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    emails = set(emails)
    existing_jobusers = get_job_coders(codingjob_id)
    existing_emails = set([ju.email for ju in existing_jobusers])

    for email in emails:
        if email in existing_emails:
            continue
        user = User.get_or_none(User.email == email)
        if not user:
            user = User.create(email=email)

        jobuser = JobUser.get_or_none(JobUser.user==user, JobUser.job==codingjob_id)
        if jobuser is None:
            JobUser.create(user=user, job_id=codingjob_id, can_code=True, can_edit=False)
        else:
            jobuser.can_code=True
            jobuser.save()

    if only_add:
        emails = emails.union(existing_emails)
    else:
        rm_emails = existing_emails - emails
        for rm_email in rm_emails:
            user = User.get_or_none(User.email == rm_email)
            jobuser = JobUser.get_or_none(JobUser.user==user, JobUser.job==codingjob_id)
            if jobuser is not None:
                jobuser.can_code=False
                jobuser.save()

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
        restricted_jobs = list(CodingJob.select().join(JobUser, JOIN.LEFT_OUTER).where(CodingJob.restricted == True, JobUser.user == user.id, JobUser.can_code == True ))
        jobs = open_jobs + restricted_jobs
    return jobs

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
