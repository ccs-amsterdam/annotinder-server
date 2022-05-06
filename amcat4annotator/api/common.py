
from amcat4annotator.db import CodingJob
from fastapi import HTTPException

   
def _job(job_id: int):
    job = CodingJob.get_or_none(CodingJob.id == job_id)
    if not job:
        HTTPException(status_code=404)
    return job