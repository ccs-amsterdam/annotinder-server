
from amcat4annotator.db import CodingJob, JobSet, get_jobset
from fastapi import HTTPException


def _job(job_id: int) -> CodingJob:
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        HTTPException(status_code=404)
    return job


def _jobset(job_id: int, user_id: int, assign_set: bool = False) -> JobSet:
    jobset = get_jobset(job_id, user_id, assign_set)
    if not jobset:
        HTTPException(status_code=404)
    return jobset
