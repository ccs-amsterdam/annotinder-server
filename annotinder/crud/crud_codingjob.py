import logging
from typing import Optional, Tuple
from sqlalchemy import true, func

from sqlalchemy.orm import Session

from annotinder.models import User, Unit, CodingJob, Annotation, JobUser, JobSetUnits, JobSet
from annotinder.crud.conditionals import check_conditionals, invalid_conditionals
from annotinder import unitserver

import datetime
from typing import List, Iterable, Optional

from fastapi import HTTPException


def create_codingjob(db: Session, title: str, codebook: dict, jobsets: list, provenance: dict, rules: dict, creator: User, units: List[dict],
                     debriefing: Optional[dict] = None, authorization: Optional[dict] = None) -> int:

    if authorization is None:
        authorization = {}
    restricted = authorization.get('restricted', False)

    job = CodingJob(title=title, rules=rules, debriefing=debriefing,
                    creator=creator, provenance=provenance, restricted=restricted)
    db.add(job)
    db.flush()
    db.refresh(job)

    add_units(db, job, units)
    add_jobsets(db, job, jobsets, codebook)
    set_job_coders(db, codingjob_id=job.id,
                   emails=authorization.get('users', []))

    # Only commits at this point, so create_codingjob can be wrapped in a try/except that rolls back changes on fail
    db.commit()
    return job


def add_units(db: Session, job: CodingJob, units: List[dict]) -> None:
    unit_list = []
    for u in units:
        unit_type = u.get('type', 'code')
        if unit_type not in ['pre', 'train', 'test', 'code', 'post']:
            raise HTTPException(status_code=400,
                                detail='Invalid unit type ("{unit_type}"). Has to be "code", "train", "test", or "survey"'.format(unit_type=unit_type))
        position = u.get('position', None)
        if position not in ['pre', 'post', None]:
            raise HTTPException(status_code=400,
                                detail='Invalid position ("{position}"). Has to be "pre", "post" or None'.format(position=position))
        unit_list.append(Unit(
            codingjob_id=job.id, external_id=u['id'], unit=u['unit'], unit_type=unit_type, position=position, conditionals=u.get('conditionals')))

    db.bulk_save_objects(unit_list)
    db.flush()


def add_jobsets(db: Session, job: CodingJob, jobsets: list, codebook: dict) -> None:
    if jobsets is None:
        jobsets = [{"name": "All"}]
    for jobset in jobsets:
        if 'name' not in jobset:
            raise HTTPException(
                status_code=400, detail='Every jobset item must have a name')
        if 'codebook' not in jobset:
            if not codebook:
                raise HTTPException(
                    status_code=400, detail='Either codebook needs to be given, or all jobsets much have a codebook')
            jobset['codebook'] = codebook
    if len({s['name'] for s in jobsets}) < len(jobsets):
        raise HTTPException(
            status_code=400, detail='jobset items must have unique names')

    for jobset in jobsets:
        db_jobset = JobSet(
            codingjob=job, jobset=jobset['name'], codebook=jobset['codebook'])
        db.add(db_jobset)
        db.flush()
        db.refresh(db_jobset)

        unit_set = []
        for position in ['pre', None, 'post']:
            for unit in prepare_unit_sets(db, jobset, position, job, db_jobset):
                unit_set.append(unit)

        db.bulk_save_objects(unit_set)
        db.flush()


def prepare_unit_sets(db, jobset, position, job, db_jobset):
    """
    Units are organized in sets relating to positions.
    - pre: units shown at the start of a job. Typically survey/experiment questions.
    - None: units with no fixed positions. Position is based on ruleset
    - post: units shown at the end of a job
    """
    if position is None:
        ids_key = 'ids'
    else:
        ids_key = position + '_ids'
    if ids_key not in jobset or jobset[ids_key] is None:
        # if no id set is specified, use all units of this type
        units = db.query(Unit.external_id).filter(
            Unit.codingjob_id == job.id, Unit.position == position).all()
        ids = [u.external_id for u in units]
    else:
        ids = jobset[ids_key]

    for i, ext_id in enumerate(ids):
        fixed_index = None
        if position == 'pre':
            fixed_index = i
        if position == 'post':
            fixed_index = i - len(ids)

        unit = db.query(Unit).filter(
            Unit.codingjob_id == job.id, Unit.external_id == ext_id).first()

        # If unit has conditionals, verify that they are possible given the codebook
        try:
            invalid_variables = invalid_conditionals(
                unit, jobset['codebook'])
        except Exception as e:
            logging.error(e)
            invalid_variables = ['unknown problem']
        if len(invalid_variables) > 0:
            raise HTTPException(
                status_code=400, detail='A unit (id = {id}) has impossible conditionals ({invalid})'.format(id=ext_id, invalid=', '.join(invalid_variables)))

        yield JobSetUnits(jobset_id=db_jobset.id, unit_id=unit.id, fixed_index=fixed_index, has_conditionals=unit.conditionals is not None)


def get_job_coders(db, codingjob_id: int) -> Iterable[str]:
    return db.query(User).outerjoin(JobUser).filter(JobUser.codingjob_id == codingjob_id, JobUser.can_code == True)


def set_job_coders(db: Session, codingjob_id: int, emails: Iterable[str], only_add: bool = False) -> Iterable[str]:
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If only_add is True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    if len(emails) == 0:
        return []
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

        jobuser = db.query(JobUser).filter(
            JobUser.user_id == user.id, JobUser.codingjob_id == codingjob_id).first()
        if jobuser is None:
            jobuser = JobUser(
                user_id=user.id, codingjob_id=codingjob_id, can_code=True, can_edit=False)
            db.add(jobuser)
        else:
            jobuser.can_code = True
        db.commit()
        db.refresh(jobuser)

    if only_add:
        emails = emails.union(existing_emails)
    else:
        rm_emails = existing_emails - emails
        for rm_email in rm_emails:
            user = db.query(User).filter(User.email == rm_email).first()
            jobuser = db.query(JobUser).filter(
                JobUser.user_id == user.id, JobUser.codingjob_id == codingjob_id).first()
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
    data = [dict(id=job.id, title=job.title, created=job.created,
                 archived=job.archived, creator=job.creator.email) for job in jobs]
    data.sort(key=lambda x: x.get('created'), reverse=True)
    return data


def get_annotations(db: Session, job_id: int):
    ann_unit_coder = db.query(Annotation, Unit, User, JobSet).join(Unit).join(
        User).join(JobSet).filter(Unit.codingjob_id == job_id).all()
    for annotation, unit, user, jobset in ann_unit_coder:
        yield {"jobset": jobset.jobset, "unit_id": unit.external_id, "coder": user.email, "annotation": annotation.annotation, "status": annotation.status}


def get_unit(db: Session, user: User, job: CodingJob, index: Optional[int]): 
    u, index = unitserver.serve_unit(db, job, user, index=index)
    if u is None:
        if index is None:
            raise HTTPException(status_code=404)
        else:
            return {'index': index}

    unit = {'id': u.id, 'unit': u.unit, 'index': index}
    a = get_unit_annotations(db, u.id, user.id)
    if a:
        unit['annotation'] = a.annotation
        unit['status'] = a.status

        # check conditionals and return failures so that coders immediately see the
        # feedback when opening the unit
        damage, report = check_conditionals(
            u, a.annotation, report_success=False)
        unit['report'] = report
    else:
        # when serving a new unit, immediately create an annotation with "IN_PROGRESS" status. This is needed
        # for crowdcoding to prevent coders that work simultaneaouly from getting served the
        # same units (because they wouldn't be annotated yet). Note that it doesn't matter that
        # much if the coder then doesn't actually finish the unit, as long as rules for blocking
        # units that have enough annotations/agreement look only at completed units
        jobuser = db.query(JobUser).filter(JobUser.codingjob_id == u.codingjob_id, 
                                           JobUser.user_id == user.id).first()
        ann = Annotation(unit_id=u.id, coder_id=user.id, annotation=[], jobset_id=jobuser.jobset_id,
                         status='IN_PROGRESS', damage=0, unit_index=index)
        db.add(ann)
        db.commit()

    return unit


def get_unit_annotations(db: Session, unit_id: int, coder_id: int):
    return db.query(Annotation).filter(Annotation.unit_id == unit_id, Annotation.coder_id == coder_id).first()


def set_annotation(db: Session, unit: Unit, coder: User, annotation: list, status: str) -> list:
    """Create a new annotation or replace an existing annotation"""
    if status not in ['DONE', 'IN_PROGRESS']:
        raise HTTPException(status_code=400, detail={
                            "error": "Status has to be 'DONE' or 'IN_PROGRESS'"})

    jobuser = db.query(JobUser).filter(JobUser.codingjob_id ==
                                       unit.codingjob_id, JobUser.user_id == coder.id).first()

    ann = db.query(Annotation).filter(Annotation.unit_id ==
                                      unit.id, Annotation.coder_id == coder.id).first()

    damage, evaluation = check_conditionals(unit, annotation)

    # force a status based on conditionals results. Also, store certain reports actions
    # in the annotation. These actions are then returned when the unit is served again.
    for action in evaluation.values():
        ca = action.get('action', None)
        if ca in ['retry', 'block']:
            status = 'RETRY'
        if ca == 'block':
            # here block entire job? could be usefull for screening (e.g., minimum age).
            None

    job = db.query(CodingJob.rules).filter(CodingJob.id == unit.codingjob_id).first()

    if ann is None:
        n_coded = db.query(Annotation).filter(
            Annotation.jobset_id == jobuser.jobset_id, Annotation.coder_id == coder.id).count()
        ann = Annotation(unit_id=unit.id, coder_id=coder.id, annotation=annotation, jobset_id=jobuser.jobset_id,
                         status=status, damage=damage, unit_index=n_coded)
        db.add(ann)
    else:
        ann.annotation = annotation
        ann.status = status
        ann.modified = datetime.datetime.now()
        if job.rules is None or not job.rules.get('heal_damage', False):
            damage = max(ann.damage, damage)
        ann.damage = damage
    db.flush()
    db.commit()

    if damage > 0:
        damage_report = process_damage(damage, db, job, jobuser, coder, unit)
    else:
        damage_report = {}

    return {"damage": damage_report, "evaluation": evaluation}


def process_damage(db: Session, job: CodingJob, jobuser: JobUser, coder: User, unit: Unit):
    """
    if damage > 0, update the total damage.
    if job.rules has max_damage, also check total damage to determine if coder has to be disqualified from job.
    """
    # get damage for all the other units for this coder+jobset.
    # (we can't include the current unit, because we then might count previous damage double) 
    damage = (db.query(func.sum(Annotation.damage))
                .filter(Annotation.jobset_id == jobuser.jobset_id, 
                        Annotation.coder_id == coder.id).scalar())
        
    # check for max damage
    if job.rules is None: return
    
    damage_report = {}
    
    if job.rules.get('show_damage', False):
        damage_report['damage'] = damage

    if 'max_damage' in job.rules:
        if job.rules.get('show_damage', False):
            damage_report['health'] = job.rules['max_damage']
        if damage > job.rules['max_damage']:
            damage_report['game_over'] = True    

    return damage_report

def get_jobset(db: Session, job_id: int, user_id: int, assign_set: bool) -> JobUser:
    jobuser = db.query(JobUser).filter(JobUser.codingjob_id ==
                                       job_id, JobUser.user_id == user_id).first()

    if jobuser is not None:
        if jobuser.jobset_id is not None:
            # if there is a jobuser with a jobset assigned, we're good.
            return db.query(JobSet).filter(JobSet.codingjob_id == job_id, JobSet.id == jobuser.jobset_id).first()

    jobsets = db.query(JobSet).filter(JobSet.codingjob_id == job_id)
    n_jobsets = jobsets.count()
    if n_jobsets == 1:
        jobset = jobsets[0]
    else:
        # better to look for the jobset with least coders!!
        current_users = db.query(JobUser).filter(
            JobUser.codingjob_id == job_id).count()
        next_jobset_index = current_users % n_jobsets
        jobset = jobsets[next_jobset_index]

    if assign_set:
        if jobuser is None:
            jobuser = JobUser(
                user_id=user_id, codingjob_id=job_id, jobset_id=jobset.id)
            db.add(jobuser)
        else:
            jobuser.jobset_id = jobset.id
        db.commit()

    return jobset
