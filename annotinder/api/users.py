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
from annotinder.models import User, CodingJob

from annotinder import mail

models.Base.metadata.create_all(bind=engine)

app_annotator_users = APIRouter(prefix="/users", tags=["annotator users"])


@app_annotator_users.post("/me/token", status_code=200)
def get_my_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Get a token via password login
    """
    u = crud_user.get_user_by_email(db, form_data.username)

    if u.failed_logins >= 5:
        time_since_block = datetime.now() - datetime.fromtimestamp(u.failed_login_timestamp)
        minutes = math.floor(time_since_block.total_seconds() / 60)
        if minutes < 15:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Too many failed login attempts. You can try again in {minutes} minutes".format(minutes=15-minutes))
        u.failed_logins = 0   

    user = crud_user.verify_password(
        db, email=form_data.username, password=form_data.password)
    if not user:
        u.failed_login_timestamp = math.floor(datetime.now().timestamp())
        u.failed_logins = u.failed_logins + 1
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Incorrect username or password")
    
    u.failed_logins = 0
    db.commit()
    return dict(token=get_token(user))


@app_annotator_users.get("/me/login", status_code=200)
def verify_my_token(db: Session = Depends(get_db), user: User = Depends(auth_user)):
    """
    Login verifies (and optionally refreshes?) the token and 
    provides some basic user details
    """
    job = None
    if user.restricted_job is not None:
        j = db.query(CodingJob).filter(CodingJob.id == user.restricted_job).first()
        if j is not None:
            job = j.title

    return {"token": get_token(user),
            "user_id": user.id,
            "email": user.email,
            "name": user.name,
            "is_admin": user.is_admin,
            "restricted_job": user.restricted_job,
            "restricted_job_label": job}


@app_annotator_users.get("/{user_id}/token")
def get_user_token(user_id: int, user: User = Depends(auth_user), db: Session = Depends(get_db)):
    """
    Get the token for the given user
    """
    check_admin(user)
    user = crud_user.get_user(db, user_id)
    return {"token": get_token(user)}


@app_annotator_users.post("/{email}/password", status_code=204)
def set_password(email: str,
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

    if not (email == 'me' or email == user.email):
        check_admin()
    crud_user.change_password(db, email, password)

    return Response(status_code=204)

@app_annotator_users.post("/{user_id}/admin", status_code=204)
def create_admin(email: str,
                 user: User = Depends(auth_user),
                 db: Session = Depends(get_db)):
    """
    Turn an existing user into an admin
    """
    check_admin()
    crud_user.create_admin(db, email)
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
        u = crud_user.register_user(
            db, user['name'], user['email'], user.get('password', None), user.get('admin', False))
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
    u = crud_user.get_user_by_email(db, email)
    
    if u.tmp_login_secret is not None:
        minutes_ago = datetime.now() - timedelta(minutes=10)
        if u.tmp_login_secret['expires'] > minutes_ago.timestamp():
            raise HTTPException(status_code=429,
                            detail="Can only send magic link once every 10 minutes")
    
    secret = "%06d" % random.randint(0,999999)
    expires_date = datetime.now() + timedelta(minutes=20)
    expires = math.floor(expires_date.timestamp())
    u.tmp_login_secret = dict(secret=secret, expires=expires)
    db.commit()

    mail.send_magic_link(u.name, u.email, secret)


@app_annotator_users.get("/{email}/secret", status_code=200)
def redeem_magic_link(email: str, 
                      secret: int = Query(None, description="Secret send by magic link"), 
                      password: str = Query(None, description="Optional password. If given, uses this as new password"), 
                      db: Session = Depends(get_db)):
    """
    """
    if secret is None:
        raise HTTPException(status_code=404,
                        detail="No secret provided")

    u = crud_user.get_user_by_email(db, email)
    if u is None:
        raise HTTPException(status_code=404,
                        detail="Invalid email address")
    
    if u.tmp_login_secret is None or int(u.tmp_login_secret['secret']) != secret:
        raise HTTPException(status_code=401,
                        detail="Invalid secret")
    if u.tmp_login_secret['expires'] < datetime.now().timestamp():
        raise HTTPException(status_code=401,
                        detail="Secret has expired")

    if password is not None:
        crud_user.change_password(db, email, password)

    ## We could disable the magic link after succesfull use. 
    # u.tmp_login_secret = None
    # db.commit()

    return {"token": get_token(u)}

