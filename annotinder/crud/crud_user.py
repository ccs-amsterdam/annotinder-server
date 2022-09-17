import logging
from typing import Optional
from email_validator import validate_email, EmailNotValidError


from sqlalchemy import func
from sqlalchemy.orm import Session

from annotinder.models import User, CodingJob, JobSet, JobUser
from annotinder import auth
from annotinder import unitserver

def safe_email(email: str):
    try:
        email = validate_email(email).email
    except EmailNotValidError as e:
         raise HTTPException(status_code=400, detail='{email} is not a valid email address'.format(email=email))
    return email

def verify_password(db: Session, email: str, password: str):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        logging.warning(f"User {email} does not exist")
        return None
    elif not u.password:
        logging.warning(f"Password for {u} is missing")
        return None
    elif not auth.verify_password(password, u.password):
        logging.warning(f"Password for {u} did not match")
        return None
    else:
        return u


def create_guest_user(db: Session, user_id: str, restricted_job: Optional[CodingJob] = None) -> User:
    """
    Guest users only have access to one specific job, and can only login via the unique token generated on first login.
    They cannot have admin privilidges and don't have an email address. 
    """
    db_user = User(name=user_id, is_admin=False,
                   password=None, restricted_job=restricted_job)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def register_user(db: Session, username: str, email: str, password: Optional[str] = None, admin: bool = False, restricted_job: Optional[CodingJob] = None) -> User:
    """
    Registered users must have an email address
    """
    email = safe_email(email)
    u = db.query(User).filter(User.email == email).first()
    if u:
        logging.error(f"User {email} already exists!")
        return None
    hpassword = auth.hash_password(password) if password else None
    db_user = User(name=username, email=email, is_admin=admin,
                   password=hpassword, restricted_job=restricted_job)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user(db: Session, user_id: int) -> User:
    u = db.query(User).filter(User.id == user_id).first()
    return u


def change_password(db: Session, email: str, password: str):
    u = db.query(User).filter(User.email == email).first()
    if not u:
        logging.warning(f"User {u.email} does not exist")
    else:
        u.password = auth.hash_password(password)
        db.commit()


def get_users(db: Session, offset: int, n: int) -> list:
    """
    Retrieve list of registered users (only to be used in admin endpoints)
    """
    users = db.query(User).filter(User.restricted_job == None).offset(offset)
    total = users.count()
    if offset is not None: users.offset(offset)
    if n is not None: users.limit(n)
    return {
        "users": [{"id": u.id, "is_admin": u.is_admin, "name": u.name} for u in users.all()],
        "total": total
    }


def get_user_jobs(db: Session, user: User):
    """
    Get a list of coding jobs, including progress information
    """
    if user.restricted_job is not None:
        jobs = db.query(CodingJob).filter(
            CodingJob.id == user.restricted_job).all()
    else:
        open_jobs = db.query(CodingJob).filter(
            CodingJob.restricted == False).all()
        restricted_jobs = db.query(CodingJob).join(JobUser).filter(
            CodingJob.restricted == True, JobUser.user_id == user.id, JobUser.can_code == True).all()
        jobs = open_jobs + restricted_jobs

    jobs_with_progress = []
    for job in jobs:
        if job.archived:
            continue
        data = {"id": job.id, "title": job.title, "created": job.created,
                "creator": job.creator.name, "archived": job.archived}

        jobuser = db.query(JobUser).filter(JobUser.codingjob_id == job.id, JobUser.user_id == user.id).first()
        if jobuser is not None:
            progress_report = unitserver.get_progress_report(db, jobuser)
            data["n_total"] = progress_report['n_total']
            data["n_coded"] = progress_report['n_coded']
            data["modified"] = progress_report['last_modified']
        jobs_with_progress.append(data)

    jobs_with_progress.sort(key=lambda x: x.get('created') if x.get(
        'modified') == None else x.get('modified'), reverse=True)

    return jobs_with_progress
