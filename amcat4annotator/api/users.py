from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Body, Depends
from fastapi.security import OAuth2PasswordRequestForm

from peewee import fn

from amcat4annotator import auth, rules
from amcat4annotator.db import Unit, Annotation, User, get_user_jobs, get_user_data
from amcat4annotator.auth import check_admin

app_annotator_users = APIRouter(prefix="/users", tags=["annotator users"])


@app_annotator_users.post("/me/token", status_code=200)
def get_my_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Get a token via password login
    """
    user = auth.verify_password(username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    return {"token": auth.get_token(user)}

@app_annotator_users.get("/me/token")
def verify_my_token(user: User = Depends(auth.authenticated_user)):
    """
    Verify a token, and get basic user information
    """
    return {"token": auth.get_token(user),
            "email": user.email,
            "is_admin": user.is_admin,
            "restricted_job": user.restricted_job}

@app_annotator_users.get("/{email}/token")
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

@app_annotator_users.post("/{email}/password", status_code=204)
def set_password(email: str,
                 password: str = Body(None, description="The new password"),
                 user: User = Depends(auth.authenticated_user)):

    if not password:
        return HTTPException(status_code = 400, detail={"error": "Body needs to have password"})

    if email == "me":
        user = User.get(User.email == user.id)
    else:
        if email != user.id:
            check_admin()
        user = User.get(User.email == email)

    user.password = auth.hash_password(password)
    user.save()
    return Response(status_code=204)

@app_annotator_users.get("")
def get_users(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of all users
    """
    check_admin(user)
    users = get_user_data()
    return {"users": users}


@app_annotator_users.post("", status_code=204)
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


@app_annotator_users.get("/me/codingjob")
def get_my_jobs(user: User = Depends(auth.authenticated_user)):
    """
    Get a list of coding jobs
    Currently: email, is_admin, (active) jobs,
    """
    jobs = get_user_jobs(user)

    jobs_with_progress = []
    for job in jobs:
        if job.archived: continue
        data = {"id": job.id, "title": job.title, "created": job.created, "creator": job.creator.email}
        
        progress_report = rules.get_progress_report(job, user)
        data["n_total"] = progress_report['n_total']
        data["n_coded"] = progress_report['n_coded']

        annotations = Annotation.select().join(Unit).where(Unit.codingjob == job.id, Annotation.coder == user.id, Annotation.status != 'IN_PROGRESS')
        data["modified"] = annotations.select(fn.MAX(Annotation.modified)).scalar() or 'NEW'

        jobs_with_progress.append(data)

    jobs_with_progress.sort(key=lambda x: x.get('created') if x.get('modified') == 'NEW' else x.get('modified'), reverse=True)
    
    return {"jobs": jobs_with_progress}


