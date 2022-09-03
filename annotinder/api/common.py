
from annotinder.models import CodingJob, JobSet, User
from fastapi import HTTPException
from annotinder.crud import crud_codingjob
from sqlalchemy.orm import Session



def _job(db: Session, job_id: int) -> CodingJob:
    job = db.query(CodingJob).filter(CodingJob.id == job_id).first()
    if not job:
        HTTPException(status_code=404)
    return job


def _jobset(db: Session, user: User, job_id: int) -> JobSet:
    jobset = crud_codingjob.get_jobset(db, user, job_id)
    if not jobset:
        HTTPException(status_code=404)
    return jobset

