import json
import os
import sys
import datetime
from enum import Enum
from typing import List, Iterable, Optional
from contextvars import ContextVar

from fastapi import HTTPException

from peewee import DateTimeField, Model, CharField, IntegerField, SqliteDatabase, AutoField, TextField, ForeignKeyField, \
    BooleanField, JOIN, chunked, _ConnectionState

STATUS = Enum('Status', ['NOT_STARTED', 'IN_PROGRESS', 'DONE', 'SKIPPED'])


# There's some magic happening here as described in 
# https://fastapi.tiangolo.com/advanced/sql-databases-peewee/
# honestly, we should just move to sqlalchemy or something
db_name = os.environ.get("ANNOTATOR_DB_NAME", "annotator.db")
if not db_name:
    print(f"Note: Using database {db_name}, user ANNOTATOR_DB_NAME to change", file=sys.stderr)
    db_name = ":memory:"
db_state_default = {"closed": None, "conn": None, "ctx": None, "transactions": None}
db_state = ContextVar("db_state", default=db_state_default.copy())


class PeeweeConnectionState(_ConnectionState):
    def __init__(self, **kwargs):
        super().__setattr__("_state", db_state)
        super().__init__(**kwargs)

    def __setattr__(self, name, value):
        self._state.get()[name] = value

    def __getattr__(self, name):
        return self._state.get()[name]


db = SqliteDatabase(db_name, pragmas={'foreign_keys': 1}, check_same_thread=False)
db._state = PeeweeConnectionState()


class JSONField(TextField):
    def db_value(self, value):
        return json.dumps(value)

    def python_value(self, value):
        if value is not None:
            return json.loads(value)


class User(Model):
    id = AutoField()
    email = CharField(max_length=512, unique=True)
    is_admin = BooleanField(default=False)
    restricted_job = IntegerField(default=None, null=True)
    password = CharField(max_length=512, null=True)

    class Meta:
        database = db


class CodingJob(Model):
    id = AutoField()
    title = CharField()
    provenance = JSONField()
    rules = JSONField()
    debriefing = JSONField(default=None, null=True)
    creator = ForeignKeyField(User, on_delete='CASCADE')
    restricted = BooleanField(default=False)
    created = DateTimeField(default=datetime.datetime.now())
    archived = BooleanField(default=False)

    class Meta:
        database = db


class Unit(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE', index=True)
    external_id = CharField(max_length=512, index=True)  
    unit = JSONField()
    gold = JSONField(default=None, null=True)

    class Meta:
        database = db
        indexes = ((('codingjob', 'external_id'), True),)  # means that this combination should be unique


class JobSet(Model):
    id = AutoField()
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE', index=True, backref='jobsets')
    jobset = CharField(max_length=512, null=True)  
    codebook = JSONField(null=True)
    has_unit_set = BooleanField()
    
    class Meta:
        database = db
        indexes = ((('codingjob', 'jobset'), True),)


class UnitSet(Model):
    jobset = ForeignKeyField(JobSet, on_delete="CASCADE", backref='unitset')
    unit = ForeignKeyField(Unit, on_delete="CASCADE", backref='unitset')

    class Meta:
        database = db


class JobUser(Model):
    user = ForeignKeyField(User, on_delete='CASCADE', index=True)
    codingjob = ForeignKeyField(CodingJob, on_delete='CASCADE', index=True)
    jobset = CharField(max_length=512, null=True) 
    can_code = BooleanField(default=True)
    can_edit = BooleanField(default=False)

    class Meta:
        database = db
        indexes = ((('user', 'codingjob'), True),)


class Annotation(Model):
    id = AutoField()
    unit = ForeignKeyField(Unit, on_delete='CASCADE')
    coder = ForeignKeyField(User, on_delete='CASCADE')
    jobset = CharField(max_length=512, null=True) 
    status = CharField(max_length=64, default=STATUS.DONE.name)
    modified = DateTimeField(default=datetime.datetime.now)
    annotation = JSONField()

    class Meta:
        database = db
        indexes = ((('unit', 'coder'), True),)


def create_codingjob(title: str, codebook: dict, jobsets: list, provenance: dict, rules: dict, creator: User, units: List[dict],
                     debriefing: Optional[dict], authorization: Optional[dict] = None) -> int:

    if authorization is None:
        authorization = {}
    restricted = authorization.get('restricted', False)
    job = CodingJob.create(title=title, rules=rules, debriefing=debriefing, creator=creator, provenance=provenance, restricted=restricted)

    units = [{'codingjob': job, 'external_id': u['id'], 'unit': u['unit'], 'gold': u.get('gold')} for u in units]
    for batch in chunked(units, 100):
        Unit.insert_many(batch).execute() 

    users = authorization.get('users', [])
    if users:
        set_job_coders(codingjob_id=job.id, emails=users)

    with db.atomic():
        add_jobsets(job, jobsets, codebook)
    return job


def add_jobsets(job: CodingJob, jobsets: list, codebook: dict) -> None:
    if jobsets is None: 
        jobsets = [{"name": "All"}]
    for jobset in jobsets:
        if 'name' not in jobset:
            raise HTTPException(status_code=400, detail='Every jobset item must have a name')
        if 'codebook' not in jobset: 
            if not codebook:
                raise HTTPException(status_code=400, detail='Either codebook needs to be given, or all jobsets much have a codebook')
            jobset['codebook'] = codebook
    if len({s['name'] for s in jobsets}) < len(jobsets):
        raise HTTPException(status_code=400, detail='jobset items must have unique names')

    for jobset in jobsets:
        has_unit_set = 'unit_set' in jobset and jobset['unit_set'] is not None
        jobset_id = JobSet.create(codingjob=job, jobset=jobset['name'], codebook=jobset['codebook'], has_unit_set=has_unit_set)
        if has_unit_set:
            unit_set = [{"jobset": jobset_id, "unit": Unit.select(Unit.id).where(Unit.codingjob == job, Unit.external_id == ext_id)} for ext_id in jobset['unit_set']]
        else:
            unit_set = [{"jobset": jobset_id, "unit": u} for u in Unit.select(Unit.id).where(Unit.codingjob == job)]
        for batch in chunked(unit_set, 100):
            UnitSet.insert_many(batch).execute()
        


def get_job_coders(codingjob_id: int) -> Iterable[str]:
    return list(User.select(User.email).join(JobUser, JOIN.LEFT_OUTER).where(JobUser.codingjob == codingjob_id, JobUser.can_code == True))
    

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

        jobuser = JobUser.get_or_none(JobUser.user == user, JobUser.codingjob == codingjob_id)
        if jobuser is None:
            JobUser.create(user=user, codingjob_id=codingjob_id, can_code=True, can_edit=False)
        else:
            jobuser.can_code=True
            jobuser.save()

    if only_add:
        emails = emails.union(existing_emails)
    else:
        rm_emails = existing_emails - emails
        for rm_email in rm_emails:
            user = User.get_or_none(User.email == rm_email)
            jobuser = JobUser.get_or_none(JobUser.user == user, JobUser.codingjob == codingjob_id)
            if jobuser is not None:
                jobuser.can_code = False
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
    data = [dict(id=job.id, title=job.title, created=job.created, archived=job.archived, creator=job.creator.email) for job in jobs]
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
        restricted_jobs = list(CodingJob.select().join(JobUser, JOIN.LEFT_OUTER).where(CodingJob.restricted == True, JobUser.user == user.id, JobUser.can_code == True))
        jobs = open_jobs + restricted_jobs
    return jobs

def set_annotation(unit: Unit, coder: User, annotation: dict, status: Optional[str] = None) -> Annotation:
    """Create a new annotation or replace an existing annotation"""
    jobuser = JobUser.get(JobUser.codingjob == unit.codingjob, JobUser.user == coder)

    if status:
        status = status.upper()
        assert hasattr(STATUS, status)
    else:
        status = STATUS.DONE.name

    ann = Annotation.get_or_none(unit=unit.id, coder=coder.id)
    if ann is None:
        return Annotation.create(unit=unit.id, coder=coder.id, annotation=annotation, jobset=jobuser.jobset, status=status)
    else:
        ann.annotation = annotation
        ann.status = status
        ann.modified = datetime.datetime.now()
        ann.save()
        return ann


def get_jobset(job_id: int, user_id: int, assign_set: bool) -> JobUser:
    jobuser = JobUser.get_or_none(JobUser.codingjob == job_id, JobUser.user == user_id)

    if jobuser is not None:
        if jobuser.jobset is not None:
            ## if there is a jobuser with a jobset assigned, we're good.
            return JobSet.get(JobSet.codingjob == job_id, JobSet.jobset == jobuser.jobset)
            
    
    jobsets = JobSet.select().where(JobSet.codingjob == job_id)
    n_jobsets = jobsets.count()
    if n_jobsets == 1:
        jobset = jobsets[0]
    else:
        current_users = JobUser.select().where(JobUser.codingjob == job_id).count()
        next_jobset_index = current_users % n_jobsets
        jobset = jobsets[next_jobset_index]

    if assign_set: 
        if jobuser is None:
            jobuser = JobUser.create(user=user_id, codingjob=job_id, jobset=jobset.jobset)
        else:
            jobuser.jobset = jobset.jobset
            jobuser.save()

    return jobset

    
def get_jobset_units(jobset: JobSet):
    """
    Returns a peewee query that selects the units assigned to a jobset,
    or all units if the jobset does not have a specific unit_set
    """
    return Unit.select().join(UnitSet).where(UnitSet.jobset == jobset).switch(Unit)
    
#TODO: is it good practice to always call this on import?
db.create_tables([CodingJob, JobSet, Unit, Annotation, User, JobUser, UnitSet])
