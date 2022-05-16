from typing import Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from amcat4annotator.models import Unit, User, Annotation, CodingJob, JobSetUnits
from amcat4annotator.crud import crud_codingjob

class ValidationError(Exception):
    pass

class RuleSet:
    """
    A Rule set encodes the 'business logic' of the back-end:
    - How should units be distributed over coders
    - Is coding limited to specific coders?
    - Can coders scroll backwards/forwards
    - What Q/A measures are in place?
    """
    def __init__(self, db: Session, rules: dict):
        self.db = db
        self.rules = rules

    def validate_codingjob(self, job: dict):
        """
        Is the current job acceptable for this rule set?
        If not, raises ValidatoinError specifying the problem(s)
        """
        pass

    def get_progress(self, job: CodingJob, coder: User) -> dict:
        """
        Return the progress report for this job, including seek permissions
        """              
        return dict(
            n_coded=self.coded(job, coder).count(),
            n_total=self.n_total(job, coder),
            seek_backwards=self.can_seek_backwards,
            seek_forwards=self.can_seek_forwards,
        )

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        """
        Get a specific unit by index. Note that this index is specific for a CodingJob X User. 
        The first item in a CodingJob or user 1 is not necesarily the same as for user 2.  
        Returns None if index could not be found
        """
        raise NotImplementedError()

    def get_next_unit(self, job: CodingJob, coder: User) -> Tuple[Optional[Unit], int]:
        """
        Like seek_unit, but without specifying an index. The next unit will then be determined
        by some rule specific method (e.g., order in DB, prioritizing units least coded by others).
        Returns two values. First is the Unit, which can be None if missing. Second is the unit index. 
        """
        raise NotImplementedError()

    def get_unit_in_progress(self, job: CodingJob, coder: User):
        """
        Get the first unit currently in progress.
        Return None if none in progress.
        """
        in_progress = self.db.query(Annotation.unit_id).join(Unit).filter(Unit.codingjob_id == job.id, Annotation.coder_id == coder.id, Annotation.status == 'IN_PROGRESS').first()
        if in_progress:
            return self.db.query(Unit).filter(Unit.id == in_progress.unit_id).first()
        return None

    @property
    def can_seek_backwards(self):
        if 'can_seek_backwards' in self.rules: return self.rules['can_seek_backwards']
        return True

    @property
    def can_seek_forwards(self):
        if 'can_seek_forwards' in self.rules: return self.rules['can_seek_forwards']
        return False

    def units(self, job: CodingJob, coder: User, assign_set: bool=True):
        """
        Get all units in a job
        """
        jobset = crud_codingjob.get_jobset(self.db, job.id, coder.id, assign_set)
        return self.db.query(Unit).join(JobSetUnits).filter(JobSetUnits.jobset_id == jobset.id)
        
    def coded(self, job: CodingJob, coder: User): 
        """
        Get coded units for a given job and user
        """
        return self.db.query(Annotation).join(Unit).filter(Unit.codingjob_id == job.id, Annotation.coder_id == coder.id, Annotation.status != 'IN_PROGRESS')

    def n_total(self, job: CodingJob, coder: User):
        """
        Total number of units that a user can code.
        This is separate from just unsing self.units().count() because a ruleset might specify an alternative (like units_per_coder in CrowdCoding)
        Also note that we set assign_set to False here so that a uses is not yet assigned the jobset if they just view the number if units in a job.
        """
        return self.units(job, coder, assign_set=False).count()

    

    



class FixedSet(RuleSet):
    """
    Each coder receives the units in the same order as loaded into the DB.
    """
    def get_next_unit(self, job: CodingJob, coder: User) -> Tuple[Optional[Unit], int]:
        unit_index = self.coded(job, coder).count()

        # (1) Is there a unit currently IN_PROGRESS?
        in_progress = self.get_unit_in_progress(job, coder)
        if in_progress:
            return in_progress, unit_index

        # (2) select the next unit
        return self.get_unit(job, coder, unit_index), unit_index

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        # (1) if seeking is restricted, return None if restriction is violated
        if not self.can_seek_forwards or not self.can_seek_backwards:
            coded = self.coded(job, coder).count()
            if self.can_seek_forwards == False & index >= coded:
                return None
            if self.can_seek_backwards == False & index < coded: 
                return None

        # (2) retrieve the unit
        return self.get_unit(job, coder, index)

    def n_total(self, job: CodingJob, coder: User):
        # If sets are specified, n is set length. Otherwise n is total number of units

        # We call units with assign_set = False to prevent that the user is assigned
        # to a set if they only viewed the number of items in the job. Note that this also means
        # that a coder might see that a job has x number of units, but if they start the number 
        # might be different if in the meantime another coder started the job (and number of items per set are different)
        units = self.units(job, coder, False)
        return units.count()

    def get_unit(self, job: CodingJob, coder: User, index: int):
        units = self.units(job, coder)
        if index < units.count():
            return units[index]       
        return None


    



class CrowdCoding(RuleSet):
    """
    Prioritizes coding the entire set as fast as possible using multiple coders.
    """
    def get_next_unit(self, job: CodingJob, coder: User) -> Tuple[Optional[Unit], int]:
        unit_index = self.coded(job, coder).count()
        if unit_index >= self.n_total(job, coder):
            return None, unit_index

        # (1) Is there a unit currently IN_PROGRESS?
        in_progress = self.get_unit_in_progress(job, coder)
        if in_progress:
            return in_progress, unit_index

        # for the following steps, need to have the unit selection for the user's jobset
        # and the jobset itself for looking only at annotations from other users in the same set
        jobset = crud_codingjob.get_jobset(self.db, job.id, coder.id, True)

        # (2) Is there a unit left in the jobset that has not yet been annotated by anyone?
        uncoded = self.db.query(JobSetUnits).outerjoin(Annotation, JobSetUnits.jobset_id == Annotation.jobset_id).filter(JobSetUnits.jobset_id == jobset.id, Annotation.id == None).first()        
        if uncoded:
            return self.db.query(Unit).filter(Unit.id == uncoded.unit_id).first(), unit_index

        # (3) select a unit from the jobset that is uncoded by me, and least coded by anyone else in the same jobset
        coded = self.db.query(Annotation.unit_id).filter(Annotation.jobset_id == jobset.id, Annotation.coder_id == coder.id).all()
        coded_id = [a.unit_id for a in coded] 
        
        least_coded = (
            self.db.query(JobSetUnits.unit_id).outerjoin(Annotation, JobSetUnits.jobset_id == Annotation.jobset_id)
            .filter(JobSetUnits.jobset_id == jobset.id, JobSetUnits.unit_id.not_in(coded_id))
            .group_by(JobSetUnits.unit_id)
            .order_by(func.count(Annotation.id))
            .first()
        )
        if least_coded:
            return self.db.query(Unit).filter(Unit.id == least_coded.unit_id).first(), unit_index

        # No units were selected, so done coding I guess?
        # (should we add a check for whether n_coded == self.n_total(job,coder) ?)
        return None, unit_index

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        if index >= self.n_total(job, coder):
            return None

        coded = self.db.query(Unit.id).join(Annotation).where(Unit.codingjob_id == job.id, Annotation.coder_id == coder.id).all()
        if index >= len(coded):
            return None
        if self.can_seek_backwards == False & index < len(coded): 
            return None
        return self.db.query(Unit).filter(Unit.id == coded[index].id).first()

    def n_total(self, job: CodingJob, coder: User):
        """
        For CrowdCoding, the number of units can be limited with the units_per_coder setting
        """
        n_units = self.units(job, coder, assign_set=False).count()
        if 'units_per_coder' in self.rules: 
            return min(self.rules['units_per_coder'], n_units)
        return n_units


def get_ruleset(db: Session, rules: dict) -> RuleSet:
    ruleset_class = {
        'crowdcoding': CrowdCoding,
        'fixedset': FixedSet,
    }[rules['ruleset']]
    return ruleset_class(db, rules)


def get_next_unit(db, job: CodingJob, coder: User) -> Optional[Unit]:
    """Return the next unit to code, or None if coder is done"""
    unit, i = get_ruleset(db, job.rules).get_next_unit(job, coder)
    return unit, i

def seek_unit(db, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
    """Seek a specific unit to code by index"""
    return get_ruleset(db, job.rules).seek_unit(job, coder, index)


def get_progress_report(db, job: CodingJob, coder: User) -> dict:
    """Return a progress report dictionary"""
    return get_ruleset(db, job.rules).get_progress(job, coder)

