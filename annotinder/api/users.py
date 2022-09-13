import hashlib

from fastapi import APIRouter, HTTPException, status, Response
from fastapi.params import Body, Depends, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from annotinder import models
from annotinder.crud import crud_user
from annotinder.database import engine, get_db
from annotinder.auth import verify_jobtoken, auth_user, check_admin, get_token
from annotinder.models import User

models.Base.metadata.create_all(bind=engine)

app_annotator_users = APIRouter(prefix="/users", tags=["annotator users"])



@app_annotator_users.post("/me/token", status_code=200)
def get_my_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Get a token via password login
    """
    user = crud_user.verify_password(
        db, username=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")
    return {"token": get_token(user)}


@app_annotator_users.get("/me/token")
def verify_my_token(user: User = Depends(auth_user)):
    """
    Verify a token, and get basic user information
    """
    return {"token": get_token(user),
            "name": user.name,
            "is_admin": user.is_admin,
            "restricted_job": user.restricted_job}


@app_annotator_users.get("/{name}/token")
def get_user_token(name: str, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get the token for the given user
    """
    check_admin(user)
    user = crud_user.get_user(db, name)
    if not user:
        raise HTTPException(status_code=404)
    return {"token": get_token(user)}


@app_annotator_users.post("/{name}/password", status_code=204)
def set_password(name: str,
                 password: str = Body(None, description="The new password"),
                 user: User = Depends(auth_user),
                 db: Session = Depends(get_db)):
    """
    Set a new password. Regular users can set only their own password.
    Admin users can set everyone's password
    """

    if not password:
        raise HTTPException(status_code=400, detail={
                            "error": "Body needs to have password"})

    if not (name == 'me' or name == user.name):
        check_admin()
    crud_user.change_password(db, name, password)

    return Response(status_code=204)


@app_annotator_users.get("")
def get_users(offset: int = Query(None, description="Offset in User table"),
              n: int = Query(None, description="Number of users"),
              
              user: User = Depends(auth_user), 
              db: Session = Depends(get_db)):
    """
    Get a list of all users
    """
    check_admin(user)
    return crud_user.get_users(db, offset, n)
    

@app_annotator_users.post("", status_code=204)
def add_users(users: list = Body(None, description="An array of dictionaries with the keys: name, password, admin", embed=True),  # notice the embed, because users is (currently) only key in body
              user: User = Depends(auth_user),
              db: Session = Depends(get_db)):
    """
    Create new users.
    """

    check_admin(user)

    if users is None:
        raise HTTPException(status_code=404, detail='Body needs to have users')

    for user in users:
        crud_user.create_user(
            db, user['name'], user['password'], user['admin'])
    return Response(status_code=204)


@app_annotator_users.get("/me/codingjob")
def get_my_jobs(user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get a list of coding jobs
    Currently: name, is_admin, (active) jobs,
    """
    jobs = crud_user.get_user_jobs(db, user)
    return {"jobs": jobs}


@app_annotator_users.get("/jobtoken")
def redeem_job_token(token: str = Query(None, description="A token for getting access to a specific coding job"),
                     user_id: str = Query(None, description="Optional, a user ID"),
                     db: Session = Depends(get_db)):
    """
    Convert a job token into a 'normal' token.
    Should be called with a token and optional user_id argument
    """
    job = verify_jobtoken(db, token)
    if not job:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Job token not valid")
    if not user_id:
        x = hashlib.sha1()
        n_users = db.query(User).count()
        x.update(str(n_users).encode('utf-8'))
        user_id = x.hexdigest()
    name = f"jobuser__{job.id}__{user_id}"
    user = crud_user.get_user(db, name)
    if not user:
        user = crud_user.create_user(db, name, restricted_job=job.id)
    return {"token": get_token(user),
            "job_id": job.id,
            "name": user.name,
            "is_admin": user.is_admin}
