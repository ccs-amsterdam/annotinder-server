import hashlib
import random, math
from datetime import datetime, timedelta
from typing import Union

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
        db, email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")
    
    return dict(token=get_token(user))


@app_annotator_users.get("/me/login", status_code=200)
def verify_my_token(user: User = Depends(auth_user)):
    """
    Login verifies (and optionally refreshes?) the token and 
    provides some basic user details
    """
    return {"token": get_token(user),
            "name": user.name,
            "is_admin": user.is_admin,
            "restricted_job": user.restricted_job}


@app_annotator_users.get("/{user_id}/token")
def get_user_token(user_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get the token for the given user
    """
    check_admin(user)
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404)
    return {"token": get_token(user)}


@app_annotator_users.post("/{user_id}/password", status_code=204)
def set_password(user_id: Union[str,int],
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

    if not (user_id == 'me' or user_id == user.id):
        check_admin()
    crud_user.change_password(db, user.id, password)

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
def add_users(users: list = Body(None, description="An array of dictionaries with the keys: name, email, password, admin", embed=True),  # notice the embed, because users is (currently) only key in body
              user: User = Depends(auth_user),
              db: Session = Depends(get_db)):
    """
    Create new users.
    """

    check_admin(user)

    if users is None:
        raise HTTPException(status_code=404, detail='Body needs to have users')

    for user in users:
        crud_user.register_user(
            db, user['name'], user['email'], user['password'], user['admin'])
    return Response(status_code=204)


@app_annotator_users.get("/me/codingjob")
def get_my_jobs(user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get a list of coding jobs
    Currently: name, is_admin, (active) jobs,
    """
    jobs = crud_user.get_user_jobs(db, user)
    return {"jobs": jobs}


@app_annotator_users.get("/{email}/magiclink", status_code=200)
def request_magic_link(email: str, db: Session = Depends(get_db)):
    """
    Logging in to a registered account has two routes (if the email address exists).
    If the user doesn't have a password, immediately send a login link via email.
    If the user does have a password, return 
    """
    email = crud_user.safe_email(email)
    u = db.query(User).filter(User.email == email).first()
    if u is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User doesn't exist")
    
    if u.tmp_login_secret is not None:
        if u.tmp_login_secret['expires'] < datetime.now().timestamp():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Magic link already sent")
    
    secret = "%06d" % random.randint(0,999999)
    expires_date = datetime.now() + timedelta(minutes=15)
    expires = math.floor(expires_date.timestamp())
    u.tmp_login_secret = dict(secret=secret, expires=expires)
    db.commit()

    ## just for testing!! This should go via email
    return dict(secret=secret, expires=expires)


