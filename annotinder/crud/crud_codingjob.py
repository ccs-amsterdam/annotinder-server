import logging
from typing import Optional, Tuple
from sqlalchemy import true, func

from sqlalchemy.orm import Session

from annotinder.models import User, Unit, CodingJob, Annotation, JobUser, JobSetUnit, JobSet
from annotinder.crud.conditionals import check_conditionals, invalid_conditionals
from annotinder import unitserver

import datetime
from typing import List, Iterable, Optional

from fastapi import HTTPException


def create_codingjob(db: Session, title: str, codebook: dict, jobsets: list, rules: dict, creator: User, units: List[dict],
                     debriefing: Optional[dict] = None, authorization: Optional[dict] = None) -> int:

    if authorization is None:
        authorization = {}
    restricted = authorization.get('restricted', False)

    job = CodingJob(title=title, creator=creator, restricted=restricted)
    db.add(job)
    db.flush()
    db.refresh(job)

    add_units(db, job, units)
    add_jobsets(db, job=job, jobsets=jobsets, codebook=codebook, rules=rules, debriefing=debriefing)
    set_job_coders(db, codingjob_id=job.id, emails=authorization.get('users', []))

    # Only commits at this point, so create_codingjob can be wrapped in a try/except that rolls back changes on fail
    db.commit()
    return job


def add_units(db: Session, job: CodingJob, units: List[dict]) -> None:
    unit_list = []
    for u in units:
        unit_type = u.get('type', 'code')
        if unit_type not in ['train', 'test', 'code', 'survey']:
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


def add_jobsets(db: Session, job: CodingJob, jobsets: list, codebook: dict, rules: dict, debriefing: Optional[dict]) -> None:
    if jobsets is None:
        jobsets = [{"name": "All"}]
    for jobset in jobsets:
        if 'name' not in jobset:
            raise HTTPException(
                status_code=400, detail='Every jobset item must have a name')
        if 'codebook' not in jobset:
            if not codebook:
                raise HTTPException(
                    status_code=400, detail='Either the codingjob needs to have a general codebook, or all jobsets have their own')
            jobset['codebook'] = codebook
        if 'rules' not in jobset:
            if not rules:
                raise HTTPException(
                    status_code=400, detail='Either the codingjob needs to have rules, or all jobsets have their own')
            jobset['rules'] = rules
        if 'debriefing' not in jobset:
            jobset['debriefing'] = debriefing
    if len({s['name'] for s in jobsets}) < len(jobsets):
        raise HTTPException(
            status_code=400, detail='jobset items must have unique names')

    for jobset in jobsets:
        db_jobset = JobSet(
            codingjob=job, jobset=jobset['name'], codebook=jobset['codebook'], rules=jobset['rules'], debriefing=jobset['debriefing'])
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

        yield JobSetUnit(jobset_id=db_jobset.id, unit_id=unit.id, fixed_index=fixed_index, has_conditionals=unit.conditionals is not None)


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


def get_unit(db: Session, jobuser: JobUser, index: Optional[int]): 
    
    u, index = unitserver.serve_unit(db, jobuser, index=index)
    if u is None:
        if index is None:
            raise HTTPException(status_code=404)
        else:
            return {'index': index}
    unit = {'id': u.id, 'unit': u.unit, 'index': index}

    a = get_unit_annotation(db, jobuser.codingjob_id, u.id, jobuser.user_id)
    if a:
        unit['annotation'] = a.annotation
        unit['status'] = a.status
        
        # If status is retry, check conditionals and return failures so that 
        # coders immediately see the feedback when opening the unit
        if a.status == 'RETRY':
            damage, evaluation = check_conditionals(
                 u, a.annotation, report_success=False)
            unit['report'] = {"evaluation": evaluation}
    else:
        # when serving a new unit, immediately create an annotation with "IN_PROGRESS" status. This is needed
        # for crowdcoding to prevent coders that work simultaneaouly from getting served the
        # same units (because they wouldn't be annotated yet). Note that it doesn't matter that
        # much if the coder then doesn't actually finish the unit, as long as rules for blocking
        # units that have enough annotations/agreement look only at completed units
        ann = Annotation(unit_id=u.id, codingjob_id=jobuser.codingjob_id, coder_id=jobuser.user_id, annotation=[], jobset_id=jobuser.jobset_id,
                         status='IN_PROGRESS', damage=0, unit_index=index)
        db.add(ann)
        db.commit()

    return unit


def get_unit_annotation(db: Session, codingjob_id: int, unit_id: int, coder_id: int):
    return db.query(Annotation).filter(Annotation.codingjob_id == codingjob_id, Annotation.unit_id == unit_id, Annotation.coder_id == coder_id).first()


def set_annotation(db: Session, ann: Annotation, coder: User, annotation: list, status: str) -> list:
    """Create a new annotation or replace an existing annotation"""
    if status not in ['DONE', 'IN_PROGRESS']:
        raise HTTPException(status_code=400, detail={
                            "error": "Status has to be 'DONE' or 'IN_PROGRESS'"})

    # update annotation
    ann.annotation = annotation
    ann.modified = datetime.datetime.now()
    ann.status = status
        
    #unit = db.query(Unit).filter(Unit.id == ann.unit_id).first()
    report = {"damage": {}, "evaluation": {}}
    if ann.unit.conditionals is not None:       
        damage, evaluation = check_conditionals(ann.unit, annotation)
        print(damage)

        report['evaluation'] = evaluation
        # force a status based on conditionals results. Also, store certain reports actions
        # in the annotation. These actions are then returned when the unit is served again.
        for action in evaluation.values():
            ca = action.get('action', None)
            if ca in ['retry', 'block']:
                status = 'RETRY'
            if ca == 'block':
                # not implemented. could block entire job? could be usefull for screening (e.g., minimum age).
                status = 'RETRY'
                None
        ann.status = status

        # If damage changed, process the JobUser's total damage
        if ann.damage != damage:
            print(ann.damage)
            print('hey')
            jobuser = get_jobuser(db, coder, ann.codingjob_id)
            jobset = jobuser.jobset
            if not jobset.rules.get('heal_damage', False):
                # the heal_damage rule determines whether damage can be healed if an annotator changes the annotation
                damage = max(ann.damage, damage)
            ann.damage = damage
            db.flush()
            total_damage = update_damage(db, jobuser, jobset.id, coder.id)
            report['damage'] = create_damage_report(damage, total_damage, jobset.rules)
   
    db.commit()
 
    return report


def update_damage(db: Session, jobuser: JobUser, jobset_id: int, coder_id: int):
    """
    if job.rules has max_damage, also check total damage to determine if coder has to be disqualified from job.
    """
    total_damage = (db.query(func.sum(Annotation.damage))
                      .filter(Annotation.jobset_id == jobset_id, 
                              Annotation.coder_id == coder_id).scalar())
    if total_damage is None:
        total_damage = 0
    jobuser.damage = total_damage
    db.flush()
    
    return total_damage


def create_damage_report(damage: float, total_damage: float, rules: dict):
    """
    get damage from jobuser tabel
    (so in process_damage, first update this table, then run this function)
    """
    damage_report = {}    
    if rules is None: return damage_report

    if rules.get('show_damage', False):
        damage_report['damage'] = damage
        damage_report['total_damage'] = total_damage

    if 'max_damage' in rules:
        if rules.get('show_damage', False):
            damage_report['max_damage'] = rules['max_damage']
        if total_damage > rules['max_damage']:
            damage_report['game_over'] = True    

    return damage_report

def get_jobuser(db: Session, user: User, job_id: int) -> Tuple[JobSet, JobUser]:
    jobuser = db.query(JobUser).filter(JobUser.codingjob_id ==
                                       job_id, JobUser.user_id == user.id).first()
    if jobuser is not None:
        return jobuser
    
    # If user is not yet a jobuser, check if allowed to be
    if user.restricted_job is not None and user.restricted_job != job_id:
        raise HTTPException(status_code=401, detail="User is only allowed to code job {restricted_job}".format(restricted_job=user.restricted_job))
    job = db.query(CodingJob).filter(CodingJob.id == job_id).first()
    if job.restricted:
        raise HTTPException(status_code=401, detail="This is a restricted codingjob, and this coder doesn't have access")

    # if user is allowed, pick a jobset
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

    # assign jobset to user
    if jobuser is None:
        jobuser = JobUser(user_id=user.id, codingjob_id=job_id, jobset_id=jobset.id)
        db.add(jobuser)
    else:
        jobuser.jobset_id = jobset.id
    db.flush()
    db.commit()

    return jobuser
