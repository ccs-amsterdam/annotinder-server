from typing import Optional
import logging
import re

from fastapi import APIRouter, HTTPException, Response
from fastapi.params import Query, Body, Depends


from amcat4annotator.api.common import _job, _jobset
from amcat4annotator import rules

from sqlalchemy.orm import Session

from amcat4annotator.crud import crud_codingjob
from amcat4annotator.database import engine, get_db
from amcat4annotator.authentication import auth_user, check_admin, get_jobtoken, check_job_user
from amcat4annotator.models import Unit, User, JobSetUnits

app_annotator_codingjob = APIRouter(prefix='/codingjob', tags=["annotator codingjob"])


@app_annotator_codingjob.post("", status_code=201)
def create_job(title: str = Body(None, description='The title of the codingjob'),
               codebook: dict = Body(None, description='The codebook'),
               units: list = Body(None, description='The units'),
               rules: dict = Body(None, description='The rules'),
               debriefing: dict = Body(None, description='Debriefing information'),
               jobsets: list = Body(None, description='A list of codingjob jobsets. An array of objects, with keys: name, codebook, unit_set'),
               authorization: dict = Body(None, description='A dictionnary containing authorization settings'),
               provenance: dict = Body(None, description='A dictionary containing any information about the units'),
               user: User = Depends(auth_user), 
               db: Session = Depends(get_db)):
    """
    Create a new codingjob. Body should be json structured as follows:

     {
      "title": <string>,
      "codebook": {.. blob ..}, # required, but can be omitted if specified in every jobset
      "units": [
        {"id": <string>         # An id string. Needs to be unique within a codingjob (not necessarily across codingjobs)
         "unit": {.. blob ..},
         "gold": {.. blob ..},  # optional, include correct answer here for gold questions
        }
        ..
      ],
      "rules": {
        "ruleset": <string>,
        "authorization": "open"|"restricted",  # optional, default: open
        .. additional ruleset parameters ..
      },
      "debriefing": {
        "message": <string>,
        "link": <string> (url)
      }
      "jobsets": [        # optional
        {"name": <string>,
         "codebook": <codebook>,  ## optional
         "unit_set": [<external_id>] ## optional
         }
      ]
      "authorization": {  # optional, default: {'restricted': False}
        restricted: boolean,
        users: [emails]
      },
      "provenance": {.. blob ..},  # optional
     }

    Where ..blob.. indicates that this is not processed by the backend, so can be annotator specific.
    See the annotator documentation for additional informations.

    The rules distribute how units should be distributed, how to deal with quality control, etc.
    The ruleset name specifies the class of rules to be used (currently "crowd" or "expert").
    Depending on the ruleset, additional options can be given.
    See the rules documentation for additional information
    """
    check_admin(user)
    if not title or not codebook or not units or not rules:
        raise HTTPException(status_code=400, detail='Codingjob is missing keys')

    try:
        job = crud_codingjob.create_codingjob(db, title=title, codebook=codebook, jobsets=jobsets, provenance=provenance, rules=rules, debriefing=debriefing, creator=user, units=units, authorization=authorization)
    except Exception as e:
        logging.error(e)
        raise HTTPException(status_code=400, detail='Could not create codingjob')

    return dict(id=job.id)


@app_annotator_codingjob.post("/{job_id}/settings", status_code=201)
def set_job_settings(job_id: int,
                     user: User = Depends(auth_user),
                     restricted: Optional[bool] = Body(None, description="set whether job should be restricted to authorized users"),
                     archived: Optional[bool] = Body(None, description="set whether job should be archived"), 
                     db: Session = Depends(get_db)):
    """
    Set job settings, and receive an object with all job settings.
    Payload should be an object where every settings is a key. Only the
    settings that need to be changed have to be in the object. The
    returned object will always have all settings.
    """
    check_admin(user)
    job = _job(db, job_id)
    if restricted is not None:
        job.restricted = restricted
    if archived is not None:
        job.archived = archived
    db.commit()
    return dict(restricted=job.restricted, archived=job.archived)


@app_annotator_codingjob.post("/{job_id}/users", status_code=204)
def set_job_users(job_id: int,
                  user: User = Depends(auth_user),
                  users: list = Body(None, description="An array of user emails"),
                  only_add: bool = Body(None, description="If True, only add the provided list of users, without removing existing users"), 
                  db: Session = Depends(get_db)):
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If body has an only_add argument with value True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    check_admin(user)
    crud_codingjob.set_job_coders(db, codingjob_id=job_id, emails=users, only_add=only_add)
    return Response(status_code=204)


@app_annotator_codingjob.get("/{job_id}")
def get_job(job_id: int,
            annotations: bool = Query(None, description="Boolean for whether or not to include annotations"),
            user: User = Depends(auth_user), 
            db: Session = Depends(get_db)):
    """
    Return a single coding job definition
    """
    check_admin(user)
    job = _job(db, job_id)
    units = crud_codingjob.get_units(db, job_id)
   
    cj = {
        "id": job_id,
        "title": job.title,
        "jobsets": [js for js in job.jobsets],
        "provenance": job.provenance,
        "rules": job.rules,
        "units": [u for u in units],
    }
    if annotations:
        cj['annotations'] = [a for a in crud_codingjob.get_annotations(db, job_id)]
    return cj


@app_annotator_codingjob.get("/{job_id}/details")
def get_job_details(job_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Return job details. Primarily for an admin to see progress and settings.
    """
    check_admin(user)
    job = _job(db, job_id)
    n_total = crud_codingjob.get_units(db, job_id).count()
    coders = crud_codingjob.get_job_coders(db, job_id)

    js_details = []
    for js in job.jobsets:
        name = js.jobset
        n_units = db.query(JobSetUnits).filter(JobSetUnits.jobset_id == js.id).count()
        js_details.append({"name": name, "n_units": n_units})

    data = {
        "id": job_id,
        "title": job.title,
        "jobset_details": js_details,
        "rules": job.rules,
        "restricted": job.restricted,
        "created": job.created,
        "archived": job.archived,
        "n_total": n_total,
        "users": [coder.email for coder in coders]
    }

    return data


@app_annotator_codingjob.get("/{job_id}/annotations")
def get_job_annotations(job_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Return a list with all annotations
    """
    check_admin(user)

    data = [a for a in crud_codingjob.get_annotations(db, job_id)]
    return data


@app_annotator_codingjob.get("/{job_id}/token")
def get_job_token(job_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Create a 'job token' for this job
    This allows anyone to code units on this job
    """
    check_admin(user)
    job = _job(db, job_id)
    token = get_jobtoken(job)
    return dict(token=token)


@app_annotator_codingjob.get("/{job_id}/codebook")
def get_codebook(job_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get the codebook for a specific job
    """
    job = _job(db, job_id)
    check_job_user(db, user, job)
    jobset = _jobset(db, job_id, user.id, assign_set=True)
    return jobset.codebook


@app_annotator_codingjob.get("/{job_id}/progress")
def progress(job_id, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get a user's progress on a specific job.
    """
    job = _job(db, job_id)
    check_job_user(db, user, job)
    return rules.get_progress_report(db, job, user)


@app_annotator_codingjob.get("/{job_id}/unit")
def get_unit(job_id,
             index: int = Query(None, description="The index of unit set for a particular user"),
             user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Retrieve a single unit to be coded.
    If ?index=i is specified, seek a specific unit. Otherwise, return the next unit to code
    """
    job = _job(db, job_id)
    check_job_user(db, user, job)
    if index is not None:
        index = int(index)
        u = rules.seek_unit(db, job, user, index=index)
    else:
        u, index = rules.get_next_unit(db, job, user)
    if u is None:
        raise HTTPException(status_code=404)
    result = {'id': u.id, 'unit': u.unit, 'index': index}
    a = crud_codingjob.get_unit_annotations(db, u.id, user.id)
    if a:
        result['annotation'] = a.annotation
        result['status'] = a.status
    return result


@app_annotator_codingjob.post("/{job_id}/unit/{unit_id}/annotation", status_code=204)
def post_annotation(job_id: int,
                    unit_id: int,
                    user: User = Depends(auth_user),
                    annotation: list = Body(None, description="An array of dictionary annotations"),
                    status: str = Body(None, description='The status of the annotation'), 
                    db: Session = Depends(get_db)):
                    
    """
    Set the annotations for a specific unit
    POST body should consist of a json object:
    {
      "annotation": [{..blob..}],
      "status": "DONE"|"IN_PROGRESS"|"SKIPPED"  # optional
    }
    """
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    job = _job(db, job_id)
    check_job_user(db, user, job)
    if not unit:
        raise HTTPException(status_code=404)
    if unit.codingjob_id != job_id:
        raise HTTPException(status_code=400)
    if not annotation:
        raise HTTPException(status_code=400)
    crud_codingjob.set_annotation(db, unit=unit, coder=user, annotation=annotation, status=status)
    return Response(status_code=204)


@app_annotator_codingjob.get("")
def get_all_jobs(user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get a list of all codingjobs
    """
    check_admin(user)
    jobs = crud_codingjob.get_jobs(db)
    return {"jobs": jobs}

@app_annotator_codingjob.get("/{job_id}/debriefing")
def get_debriefing(job_id: int,
                   user: User = Depends(auth_user), 
                   db: Session = Depends(get_db)):
    """
    Get a list of all codingjobs
    """
    job = _job(db, job_id)
    check_job_user(db, user, job)
    progress = rules.get_progress_report(db, job, user)
    if progress['n_coded'] != progress['n_total']:
      raise HTTPException(status_code=404, detail='Can only get debrief information once job is completed')
    
    if job.debriefing is None:
      return None
      
    job.debriefing['user_id'] = re.sub('jobuser_[0-9]+_', '', user.email)
    return job.debriefing


# TODO
# - redeem_jobtoken moet user kunnen creeren vor een 'job token' (en email/id teruggeven) [untested]
# - endpoint om 'job tokens' te kunnen aanmaken [untested]
