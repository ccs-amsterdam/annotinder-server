import logging
from typing import Optional

from sqlalchemy.orm import Session

from amcat4annotator.models import User, Unit, CodingJob, Annotation, JobUser, JobSetUnits, JobSet

import datetime
from typing import List, Iterable, Optional

from fastapi import HTTPException

def create_codingjob(db: Session, title: str, codebook: dict, jobsets: list, provenance: dict, rules: dict, creator: User, units: List[dict],
                     debriefing: Optional[dict] = None, authorization: Optional[dict] = None) -> int:

    if authorization is None:
        authorization = {}
    restricted = authorization.get('restricted', False)
    job = CodingJob(title=title, rules=rules, debriefing=debriefing, creator=creator, provenance=provenance, restricted=restricted)
    db.add(job)
    db.commit()
    db.refresh(job)

    units = [Unit(codingjob_id=job.id, external_id=u['id'], unit=u['unit'], gold=u.get('gold')) for u in units]
    db.bulk_save_objects(units)
    db.commit()

    users = authorization.get('users', [])
    if users:
        set_job_coders(db, codingjob_id=job.id, emails=users)

    add_jobsets(db, job, jobsets, codebook)
    return job


def add_jobsets(db: Session, job: CodingJob, jobsets: list, codebook: dict) -> None:
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
        db_jobset = JobSet(codingjob=job, jobset=jobset['name'], codebook=jobset['codebook'])
        db.add(db_jobset)
        db.commit()
        db.refresh(db_jobset)

        unit_set = []
        if 'unit_set' in jobset and jobset['unit_set'] is not None:
            for ext_id in jobset['unit_set']:
                unit = db.query(Unit.id).filter(Unit.codingjob_id == job.id, Unit.external_id == ext_id).first()
                unit_set.append(JobSetUnits(jobset_id=db_jobset.id, unit_id=unit.id))
        else:
            for u in db.query(Unit.id).filter(Unit.codingjob_id == job).all():
                unit_set.append(JobSetUnits(jobset_id=db_jobset.id, unit_id=u.id))
        db.bulk_save_objects(unit_set)
        db.commit()


def get_job_coders(db, codingjob_id: int) -> Iterable[str]:
    return db.query(User).outerjoin(JobUser).filter(JobUser.codingjob_id == codingjob_id, JobUser.can_code==True)    
    

def set_job_coders(db: Session, codingjob_id: int, emails: Iterable[str], only_add: bool = False) -> Iterable[str]:
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If only_add is True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    emails = set(emails)
    existing_jobusers = get_job_coders(db, codingjob_id)
    existing_emails = set([ju.email for ju in existing_jobusers])

    for email in emails:
        if email in existing_emails:
            continue
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(email=email)
            db.add(user)
            db.commit()
            db.refresh(user)

        jobuser = db.query(JobUser).filter(JobUser.user_id == user.id, JobUser.codingjob_id == codingjob_id).first()
        if jobuser is None:
            jobuser = JobUser(user_id=user.id, codingjob_id=codingjob_id, can_code=True, can_edit=False)
            db.add(jobuser)
        else:
            jobuser.can_code=True
        db.commit()
        db.refresh(jobuser)

    if only_add:
        emails = emails.union(existing_emails)
    else:
        rm_emails = existing_emails - emails
        for rm_email in rm_emails:
            user = db.query(User).filter(User.email == rm_email).first()
            jobuser = db.query(JobUser).filter(JobUser.user_id == user.id, JobUser.codingjob_id == codingjob_id).first()
            if jobuser is not None:
                jobuser.can_code = False
        db.commit()

    return list(emails)


def get_units(db: Session, codingjob_id: int) -> Iterable[Unit]:
    return db.query(Unit).filter(Unit.codingjob_id == codingjob_id)


def get_jobs(db: Session) -> list:
    """
    Retrieve all jobs. Only basic meta data. 
    """
    jobs = db.query(CodingJob).all()
    data = [dict(id=job.id, title=job.title, created=job.created, archived=job.archived, creator=job.creator.email) for job in jobs]
    data.sort(key=lambda x: x.get('created'), reverse=True)
    return data

def get_annotations(db: Session, job_id: int): 
    ann_unit_coder = db.query(Annotation, Unit, User, JobSet).join(Unit).join(User).join(JobSet).filter(Unit.codingjob_id == job_id).all()
    for annotation, unit, user, jobset in ann_unit_coder:
        yield {"jobset": jobset.jobset, "unit_id": unit.external_id, "coder": user.email, "annotation": annotation.annotation, "status": annotation.status}   
    
def get_unit_annotations(db: Session, unit_id: int, coder_id: int):
    return db.query(Annotation).filter(Annotation.unit_id == unit_id, Annotation.coder_id == coder_id).first()

def set_annotation(db: Session, unit: int, coder: User, annotation: dict, status: str) -> Annotation:
    """Create a new annotation or replace an existing annotation"""
    jobuser = db.query(JobUser).filter(JobUser.codingjob_id == unit.codingjob_id, JobUser.user_id == coder.id).first()
    
    ann = db.query(Annotation).filter(Annotation.unit_id == unit.id, Annotation.coder_id == coder.id).first()
    if ann is None:
        ann = Annotation(unit_id=unit.id, coder_id=coder.id, annotation=annotation, jobset_id=jobuser.jobset_id, status=status)
        db.add(ann)
    else:
        ann.annotation = annotation
        ann.status = status
        ann.modified = datetime.datetime.now()
    db.commit()
    return ann

def get_jobset(db: Session, job_id: int, user_id: int, assign_set: bool) -> JobUser:
    jobuser = db.query(JobUser).filter(JobUser.codingjob_id == job_id, JobUser.user_id == user_id).first()

    if jobuser is not None:
        if jobuser.jobset_id is not None:
            ## if there is a jobuser with a jobset assigned, we're good.
            return db.query(JobSet).filter(JobSet.codingjob_id == job_id, JobSet.id == jobuser.jobset_id).first()
            
    
    jobsets = db.query(JobSet).filter(JobSet.codingjob_id == job_id)
    n_jobsets = jobsets.count()
    if n_jobsets == 1:
        jobset = jobsets[0]
    else:
        ## better to look for the jobset with least coders!!
        current_users = db.query(JobUser).filter(JobUser.codingjob_id == job_id).count()
        next_jobset_index = current_users % n_jobsets
        jobset = jobsets[next_jobset_index]

    if assign_set: 
        if jobuser is None:
            jobuser = JobUser(user_id=user_id, codingjob_id=job_id, jobset_id=jobset.id)
            db.add(jobuser)
        else:
            jobuser.jobset_id = jobset.id
        db.commit()

    return jobset
