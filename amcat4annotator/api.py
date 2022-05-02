import hashlib

from typing import Optional

from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Query, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm

from amcat4annotator import auth, rules
from amcat4annotator.db import create_codingjob, Unit, CodingJob, Annotation, User, get_user_jobs, \
    get_user_data, get_jobs, set_annotation, get_jobusers, set_jobusers
from amcat4annotator.auth import check_admin, check_job_user, get_jobtoken, verify_jobtoken

app_annotator = APIRouter(tags=["annotator"])



@app_annotator.post("/users/me/token", status_code=201)
def get_my_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Get a token via password login
    """
    user = auth.verify_password(username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    return {"token": auth.get_token(user)}

def _job(job_id: int):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        abort(404)
    return job

@app_annotator.get("/users/me/token")
def verify_my_token(user: User = Depends(auth.authenticated_user)):
    """
    Verify a token, and get basic user information
    """
    return {"token": auth.get_token(user),
            "email": user.email,
            "is_admin": user.is_admin,
            "restricted_job": user.restricted_job}

@app_annotator.get("/users/{email}/token")
def get_user_token(email: str, user: User = Depends(auth.authenticated_user)):
    """
    Get the  token for the given user
    """
    check_admin(user)
    try:
        user = User.get(User.email == email)
    except User.DoesNotExist:
        raise HTTPException(status_code=404)
    return {"token": auth.get_token(user)}


@app_annotator.post("/codingjob", status_code=201)
def create_job(title: str = Body(None, description = 'The title of the codingjob'),
               codebook: dict = Body(None, description = 'The codebook'),
               units: list = Body(None, description = 'The units'),
               rules: dict = Body(None, description = 'The rules'),
               authorization: dict = Body(None, description = 'A dictionnary containing authorization settings'),
               provenance: dict = Body(None, description = 'A dictionary containing any information about the units'),
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


@app_annotator.post("/codingjob/{job_id}/settings", status_code=201)
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


@app_annotator.post("/codingjob/{job_id}/users", status_code=204)
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
    set_jobusers(codingjob_id=job_id, emails=users, only_add=only_add)
    return Response(status_code=204)


@app_annotator.get("/codingjob/{job_id}")
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


@app_annotator.get("/codingjob/{job_id}/details")
def get_job_details(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Return job details. Primarily for an admin to see progress and settings.
    """
    check_admin(user)
    job = _job(job_id)
    n_total = Unit.select().where(Unit.codingjob == job.id).count()
    jobusers = get_jobusers(job.id)
    
    data = {
        "id": job_id,
        "title": job.title,
        "codebook": job.codebook,
        "rules": job.rules,
        "restricted": job.restricted,
        "created": job.created,
        "archived": job.archived,
        "n_total": n_total,
        "users": jobusers
    }
 
    return data


@app_annotator.get("/codingjob/{job_id}/annotations")
def get_job_annotations(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Return a list with all annotations
    """
    check_admin(user)
    job = _job(job_id)
    units = list(Annotation.select(Unit, Annotation, User.email).join(Unit).where(Unit.codingjob==job).join(User, on=(Annotation.coder == User.id)).tuples().dicts().execute())
    data = [{"unit_id": u["external_id"], "coder": u["email"], "annotation": u["annotation"], "status": u["status"]} for u in units]
    return data

@app_annotator.get("/codingjob/{job_id}/token")
def get_job_token(job_id: int, user: User = Depends(auth.authenticated_user)):
    """
    Create a 'job token' for this job
    This allows anyone to code units on this job
    """
    check_admin(user)
    job = _job(job_id)
    token = get_jobtoken(job)
    return dict(token=token)


@app_annotator.get("/jobtoken")
def redeem_job_token(token: str = Query(None, description="A token for getting access to a specific coding job"),
                     user_id: str = Query(None, description="Optional, a user ID")):
    """
    Convert a job token into a 'normal' token.
    Should be called with a token and optional user_id argument
    """
    job = verify_jobtoken(token)
    if not job:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Job token not valid")
    if not user_id:
        x = hashlib.sha1()
        x.update(str(User.select().count()).encode('utf-8'))
        user_id = x.hexdigest()
    email = f"jobuser__{job.id}__{user_id}"
    user = User.get_or_none(User.email == email)
    if not user:
        user = User.create(email=email, restricted_job=job)
    return {"token": auth.get_token(user),
            "job_id": job.id,
            "email": user.email,
            "is_admin": user.is_admin}


@app_annotator.get("/codingjob/{job_id}/codebook")
def get_codebook(job_id: int, user: User = Depends(auth.authenticated_user)):
    job = _job(job_id)
    check_job_user(user, job)
    return job.codebook


@app_annotator.get("/codingjob/{job_id}/progress")
def progress(job_id, user: User = Depends(auth.authenticated_user)):
    job = _job(job_id)
    check_job_user(user, job)
    return rules.get_progress_report(job, user)


@app_annotator.get("/codingjob/{job_id}/unit")
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
    if u is not None:
        HTTPException(status_code=404)
    result = {'id': u.id, 'unit': u.unit, 'index': index}
    a = list(Annotation.select().where(Annotation.unit == u.id, Annotation.coder == user.id))
    if a:
        result['annotation'] = a[0].annotation
        result['status'] = a[0].status
    return result


@app_annotator.post("/codingjob/{job_id}/unit/{unit_id}/annotation", status_code=204)
def post_annotation(job_id: int, 
                    unit_id: int, 
                    user: User = Depends(auth.authenticated_user),
                    annotation: list = Body(None, description="An array of dictionary annotations"),
                    status: str = Body(None, description='The status of the annotation')):
    """
    Set the annotations for a specific unit
    POST body should consist of a json object:
    {
      "annotation": {..blob..},
      "status": "DONE"|"IN_PROGRESS"|"SKIPPED"  # optional
    }
    """
    unit = Unit.get_or_none(Unit.id == unit_id)
    job = _job(job_id)
    check_job_user(user, job)
    if not unit:
        HTTPException(status_code=404, detail='')
    if unit.codingjob != job:
        HTTPException(status_code=400, detail='')
    if not annotation:
        HTTPException(status_code=400, detail='')
    a = set_annotation(unit.id, coder=user.email, annotation=annotation, status=status)
    return Response(status_code=204)
    
@app_annotator.get("/codingjobs")
def get_all_jobs(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of all codingjobs
    """
    check_admin(user)
    jobs = get_jobs()
    return {"jobs": jobs}

@app_annotator.get("/users/me/codingjobs")
def get_my_jobs(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of coding jobs
    Currently: email, is_admin, (active) jobs,
    """
    jobs = get_user_jobs(user)
    return {"jobs": jobs}





@app_annotator.get("/users")
def get_users(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of all users
    """
    check_admin(user)
    users = get_user_data()
    return {"users": users}


@app_annotator.post("/users", status_code=204)
def add_users(users: list = Body(None, description="An array of dictionaries with the keys: email, password, admin", embed=True),  ## notice the embed, because users is (currently) only key in body
              user: User = Depends(auth.authenticated_user)):
    check_admin(user)

    if users is None:
        return HTTPException(status_code=404, detail='Body needs to have users')

    for user in users:
        u = User.get_or_none(User.email == user['email'])
        if u:
            continue
        password = auth.hash_password(user['password']) if user['password'] else None
        u = User.create(email=user['email'], is_admin=user['admin'], password=password)
    return Response(status_code=204)



@app_annotator.post("/password", status_code=204)
def set_password(password: str = Body(None, description="The new password"),
                 email: Optional[str] = Body(None, description="The email of the user for who to set the password (admin only)"),
                 user: User = Depends(auth.authenticated_user)):

    if not password:
        return make_response({"error": "Body needs to have password"}, 400)

    if email is not None:
        if email != user.id:
            check_admin()
        user = User.get(User.email == email)
    else:
        user = User.get(User.email == user.id)

    user.password = auth.hash_password(password)
    user.save()
    return Response(status_code=204)

# TODO
# - redeem_jobtoken moet user kunnen creeren vor een 'job token' (en email/id teruggeven) [untested]
# - endpoint om 'job tokens' te kunnen aanmaken [untested]
