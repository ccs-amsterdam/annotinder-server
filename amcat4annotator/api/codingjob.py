from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.params import Query, Body, Depends

from amcat4annotator.api.common import _job
from amcat4annotator import auth, rules
from amcat4annotator.db import create_codingjob, Unit, Annotation, User, get_jobs, set_annotation, get_job_coders, set_job_coders
from amcat4annotator.auth import check_admin, check_job_user, get_jobtoken

app_annotator_codingjob = APIRouter(prefix='/codingjob', tags=["annotator codingjob"])

@app_annotator_codingjob.post("", status_code=201)
def create_job(title: str = Body(None, description='The title of the codingjob'),
               codebook: dict = Body(None, description='The codebook'),
               units: list = Body(None, description='The units'),
               rules: dict = Body(None, description='The rules'),
               authorization: dict = Body(None, description='A dictionnary containing authorization settings'),
               provenance: dict = Body(None, description='A dictionary containing any information about the units'),
               user: User = Depends(auth.authenticated_user)):
    """
    Create a new codingjob. Body should be json structured as follows:

     {
      "title": <string>,
      "codebook": {.. blob ..},
      "authorization": {  # optional, default: {'restricted': False}
        restricted: boolean,
        users: [emails]
      }
      "rules": {
        "ruleset": <string>,
        "authorization": "open"|"restricted",  # optional, default: open
        .. additional ruleset parameters ..
      },
      "units": [
        {"id": <string>         # An id string. Needs to be unique within a codingjob (not necessarily across codingjobs)
         "unit": {.. blob ..},
         "gold": {.. blob ..},  # optional, include correct answer here for gold questions
        }
        ..
      ],
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
        return HTTPException(status_code=400, detail='Codingjob is missing keys')
    job = create_codingjob(title=title, codebook=codebook, provenance=provenance,
                           rules=rules, creator=user, units=units, authorization=authorization)
    return dict(id=job.id)


@app_annotator_codingjob.post("/{job_id}/settings", status_code=201)
def set_job_settings(job_id: int, 
                     user: User = Depends(auth.authenticated_user),
                     restricted: Optional[bool] = Body(None, description = "set whether job should be restricted to authorized users"),
                     archived: Optional[bool] = Body(None, description = "set whether job should be archived")):
    """
    Set job settings, and receive an object with all job settings. 
    Payload should be an object where every settings is a key. Only the
    settings that need to be changed have to be in the object. The 
    returned object will always have all settings.
    """
    check_admin(user)
    job = _job(job_id)
    if restricted is not None: job.restricted = restricted
    if archived is not None: job.archived = archived
    job.save()
    return dict(restricted=job.restricted, archived=job.archived)


@app_annotator_codingjob.post("/{job_id}/users", status_code=204)
def set_job_users(job_id: int, 
                  user: User = Depends(auth.authenticated_user),
                  users: list = Body(None, description="An array of user emails"),
                  only_add: bool = Body(None, description="If True, only add the provided list of users, without removing existing users")):
    """
    Sets the users that can code the codingjob (if the codingjob is restricted).
    If body has an only_add argument with value True, the provided list of emails is only added, and current users that are not in this list are kept.
    Returns an array with all users.
    """
    check_admin(user)
    set_job_coders(codingjob_id=job_id, emails=users, only_add=only_add)
    return Response(status_code=204)


@app_annotator_codingjob.get("/{job_id}")
def get_job(job_id: int, 
            annotations: bool = Query(None, description="Boolean for whether or not to include annotations"),
            user: User = Depends(auth.authenticated_user)):
    """
    Return a single coding job definition
    """
    check_admin(user)
    job = _job(job_id)
    units = list(Unit.select(Unit.id, Unit.gold, Unit.unit)
                     .where(Unit.codingjob==job).tuples().dicts().execute())
    cj = {
        "id": job_id,
        "title": job.title,
        "codebook": job.codebook,
        "provenance": job.provenance,
        "rules": job.rules,
        "units": units
    }
    if annotations:
        cj['annotations'] = list(Annotation.select(Annotation).join(Unit)
                 .where(Unit.codingjob == job).tuples().dicts().execute())
    return cj


@app_annotator_codingjob.get("/{job_id}/details")
def get_job_details(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Return job details. Primarily for an admin to see progress and settings.
    """
    check_admin(user)
    job = _job(job_id)
    n_total = Unit.select().where(Unit.codingjob == job.id).count()
    coders = get_job_coders(job.id)
    
    data = {
        "id": job_id,
        "title": job.title,
        "codebook": job.codebook,
        "rules": job.rules,
        "restricted": job.restricted,
        "created": job.created,
        "archived": job.archived,
        "n_total": n_total,
        "users": [coder.email for coder in coders]
    }
 
    return data


@app_annotator_codingjob.get("/{job_id}/annotations")
def get_job_annotations(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Return a list with all annotations
    """
    check_admin(user)
    job = _job(job_id)
    units = list(Annotation.select(Unit, Annotation, User.email).join(Unit).where(Unit.codingjob==job).join(User, on=(Annotation.coder == User.id)).tuples().dicts().execute())
    data = [{"unit_id": u["external_id"], "coder": u["email"], "annotation": u["annotation"], "status": u["status"]} for u in units]
    return data

@app_annotator_codingjob.get("/{job_id}/token")
def get_job_token(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Create a 'job token' for this job
    This allows anyone to code units on this job
    """
    check_admin(user)
    job = _job(job_id)
    token = get_jobtoken(job)
    return dict(token=token)


@app_annotator_codingjob.get("/{job_id}/codebook")
def get_codebook(job_id: int, user: User = Depends(auth.authenticated_user)):
    job = _job(job_id)
    check_job_user(user, job)
    return job.codebook


@app_annotator_codingjob.get("/{job_id}/progress")
def progress(job_id, user: User = Depends(auth.authenticated_user)):
    job = _job(job_id)
    check_job_user(user, job)
    return rules.get_progress_report(job, user)


@app_annotator_codingjob.get("/{job_id}/unit")
def get_unit(job_id, 
             index: int = Query(None, description="The index of unit set for a particular user"),
             user: User = Depends(auth.authenticated_user)):
    """
    Retrieve a single unit to be coded.
    If ?index=i is specified, seek a specific unit. Otherwise, return the next unit to code
    """
    job = _job(job_id)
    check_job_user(user, job)
    
    if index is not None:
        index = int(index)
        u = rules.seek_unit(job, user, index=index)
    else:
        u, index = rules.get_next_unit(job, user)
    if u is None:
        return HTTPException(status_code=404)

    result = {'id': u.id, 'unit': u.unit, 'index': index}
    a = list(Annotation.select().where(Annotation.unit == u.id, Annotation.coder == user.id))
    if a:
        result['annotation'] = a[0].annotation
        result['status'] = a[0].status
    return result


@app_annotator_codingjob.post("/{job_id}/unit/{unit_id}/annotation", status_code=204)
def post_annotation(job_id: int, 
                    unit_id: int, 
                    user: User = Depends(auth.authenticated_user),
                    annotation: list = Body(None, description="An array of dictionary annotations"),
                    status: str = Body(None, description='The status of the annotation')):
    """
    Set the annotations for a specific unit
    POST body should consist of a json object:
    {
      "annotation": [{..blob..}],
      "status": "DONE"|"IN_PROGRESS"|"SKIPPED"  # optional
    }
    """
    
    unit = Unit.get_or_none(Unit.id == unit_id)
    job = _job(job_id)
    check_job_user(user, job)
    if not unit:
        HTTPException(status_code=404)
    if unit.codingjob != job:
        HTTPException(status_code=400)
    if not annotation:
        HTTPException(status_code=400)
    a = set_annotation(unit_id = unit.id, coder=user.email, annotation=annotation, status=status)
    return Response(status_code=204)
    
@app_annotator_codingjob.get("")
def get_all_jobs(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of all codingjobs
    """
    check_admin(user)
    jobs = get_jobs()
    return {"jobs": jobs}



# TODO
# - redeem_jobtoken moet user kunnen creeren vor een 'job token' (en email/id teruggeven) [untested]
# - endpoint om 'job tokens' te kunnen aanmaken [untested]
