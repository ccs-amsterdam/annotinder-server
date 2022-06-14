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

    try:
        job = CodingJob(title=title, rules=rules, debriefing=debriefing, creator=creator, provenance=provenance, restricted=restricted)
        db.add(job)
        db.flush()
        db.refresh(job)

        units = [Unit(codingjob_id=job.id, external_id=u['id'], unit=u['unit'], type=u.get('type', None), gold=u.get('gold')) for u in units]
        db.bulk_save_objects(units)
        db.flush()

        users = authorization.get('users', [])
        if users:
            set_job_coders(db, codingjob_id=job.id, emails=users)

        add_jobsets(db, job, jobsets, codebook)
        db.commit()
    except:
        db.rollback()
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
        db.flush()
        db.refresh(db_jobset)

        def get_units(db, jobset, unit_type):
            """
            Units are organized in types. If a jobset doesn't have a set for a specific type,
            use all units of this type. Types are:
            - pre: units shown at the start of a job. Typically survey/experiment questions
            - train: units to make a training loop, commenced just after pre. units need to have 'gold'
            - test: units for testing whether coder is performing well. Will be mixed with the regular units. Need to have 'gold'
            - unit: A regular unit, to be annotated
            - post: units shown at the end of a job
            """
            ids_key = unit_type + '_ids'
            if ids_key not in jobset or jobset[ids_key] is None:
                # if no id set is specified, use all units of this type
                units = db.query(Unit.id).filter(Unit.codingjob_id == job.id, Unit.type == unit_type).all()
                ids = [u.external_id for u in units]
            else:
                ids = jobset[ids_key]
            for ext_id in ids:
                unit = db.query(Unit.id).filter(Unit.codingjob_id == job.id, Unit.external_id == ext_id).first()
                yield JobSetUnits(jobset_id=db_jobset.id, unit_id=unit.id, type=unit_type, has_gold=unit.gold is not None)
                ## TODO: This would be a good place for adding a check for whether gold can be optained with current codebook
                
        unit_set = []
        for pre_unit in get_units(db, jobset, 'pre'):
            unit_set.append(pre_unit)
        for unit in get_units(db, jobset, 'train'):
            unit_set.append(unit)
        for unit in get_units(db, jobset, 'test'):
            unit_set.append(unit)
        for unit in get_units(db, jobset, 'code'):
            unit_set.append(unit)
        for post_unit in get_units(db, jobset, 'post'):
            unit_set.append(post_unit)

        db.bulk_save_objects(unit_set)
        db.flush()


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


def set_annotation(db: Session, unit: Unit, coder: User, annotation: list, status: str) -> Annotation:
    """Create a new annotation or replace an existing annotation"""
    jobuser = db.query(JobUser).filter(JobUser.codingjob_id == unit.codingjob_id, JobUser.user_id == coder.id).first()
    
    ann = db.query(Annotation).filter(Annotation.unit_id == unit.id, Annotation.coder_id == coder.id).first()
    if ann is None:
        if ann.status == 'DONE': 
            status = 'DONE' ## cannot undo DONE
                
        ann = Annotation(unit_id=unit.id, coder_id=coder.id, annotation=annotation, jobset_id=jobuser.jobset_id, status=status)
        db.add(ann)
    else:
        ann.annotation = annotation
        ann.status = status
        ann.modified = datetime.datetime.now()
    db.commit()
    return ann


def check_gold(unit: Unit, annotation: Annotation):
    """
    If unit has a gold standard, see if annotations match it.
    This can have two consequences:
    - The coder can take damage for getting it wrong.
    - The coder can receive gold_feedback. The unit will then be marked 
      as IN_PROGRESS, and the coder can't continue before the right answer is given   
    """
    if unit.gold is None:
        return []
    gold_feedback = []
    damage = 0
    for g in unit.gold['matches']:
        ## only check gold matches for variables that have been coded
        ## (if unit is done, all variables are assumed to have been coded)
        variable_coded = unit.status == "DONE"
        found_match = False
        for a in annotation.annotation:
            if g['variable'] != a['variable']: continue
            variable_coded = True
            if g['field'] is not None: 
                if g['field'] != a['field']: continue;
            if g['offset'] is not None:
                if g['offset'] != a['offset']: continue;
            if g['length'] is not None:
                if g['length'] != a['length']: continue;

            op = g['operator'] if 'operator' in g else '=='
            if op == "==" and a['value'] == g['value']: found_match = True
            if op == "<=" and a['value'] <= g['value']: found_match = True
            if op == "<" and a['value'] < g['value']: found_match = True
            if op == ">=" and a['value'] >= g['value']: found_match = True
            if op == ">" and a['value'] > g['value']: found_match = True
            if op == "!=" and a['value'] != g['value']: found_match = True
            if found_match: continue
        if found_match: continue
        if not variable_coded: continue

        if 'damage' in g: damage += g['damage']
        if unit.gold['if_wrong'] == 'retry':
            feedback = {"variable": g['variable']}
            if (g['message']): feedback['message'] = g['message']
            gold_feedback.push(feedback)

    if 'redemption' not in unit.gold or unit.gold['redemption']:
        unit.damage = damage
    else:
        unit.damage = max(damage, unit.damage)

    if len(gold_feedback) > 0:
        unit.status = "IN_PROGRESS"
    
    return gold_feedback
    


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

    