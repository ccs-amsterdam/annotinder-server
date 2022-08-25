
from annotinder.models import CodingJob, JobSet
from fastapi import HTTPException
from annotinder.crud import crud_codingjob
from sqlalchemy.orm import Session



def _job(db: Session, job_id: int) -> CodingJob:
    job = db.query(CodingJob).filter(CodingJob.id == job_id).first()
    if not job:
        HTTPException(status_code=404)
    return job


def _jobset(db: Session, job_id: int, user_id: int, assign_set: bool = False) -> JobSet:
    jobset = crud_codingjob.get_jobset(db, job_id, user_id, assign_set)
    if not jobset:
        HTTPException(status_code=404)
    return jobset
