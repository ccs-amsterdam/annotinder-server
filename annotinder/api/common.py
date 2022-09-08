
from annotinder.models import CodingJob, JobSet, User
from fastapi import HTTPException
from annotinder.crud import crud_codingjob
from sqlalchemy.orm import Session



def _job(db: Session, job_id: int) -> CodingJob:
    job = db.query(CodingJob).filter(CodingJob.id == job_id).first()
    if not job:
        HTTPException(status_code=404)
    return job


def _jobuser(db: Session, user: User, job_id: int) -> JobSet:
    jobuser = crud_codingjob.get_jobuser(db, user, job_id)
    if not jobuser:
        HTTPException(status_code=404)
    return jobuser

