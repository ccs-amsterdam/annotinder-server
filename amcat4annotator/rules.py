from typing import Optional, Tuple

from peewee import fn, JOIN

from amcat4annotator.db import Unit, User, Annotation, CodingJob, JobUser


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
    def __init__(self, rules: dict):
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
            n_coded=self.n_coded(job, coder),
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

    @property
    def can_seek_backwards(self):
        if 'can_seek_backwards' in self.rules: return self.rules['can_seek_backwards']
        return True

    @property
    def can_seek_forwards(self):
        if 'can_seek_forwards' in self.rules: return self.rules['can_seek_forwards']
        return False

    def n_coded(self, job: CodingJob, coder: User): 
        return Annotation.select().join(Unit).where(Unit.codingjob == job.id, Annotation.coder == coder.id, Annotation.status != 'IN_PROGRESS').count()

    def n_total(self, job: CodingJob, coder: User):
        n_units = Unit.select().where(Unit.codingjob == job.id).count()
        if 'units_per_coder' in self.rules: 
            return min(self.rules['units_per_coder'], n_units)
        return n_units

class FixedSet(RuleSet):
    """
    Each coder receives the units in the same order as loaded into the DB.
    """
    def get_next_unit(self, job: CodingJob, coder: User) -> Tuple[Optional[Unit], int]:
        unit_index = self.n_coded(job, coder)
        if unit_index >= self.n_total(job, coder):
            return None, unit_index

        # (1) Is there a unit currently IN_PROGRESS?
        in_progress = list(
            Unit.select()
            .join(Annotation, JOIN.LEFT_OUTER)
            .where(Unit.codingjob == job.id, Annotation.coder == coder.id, Annotation.status == 'IN_PROGRESS')
            .limit(1).execute())
        if in_progress:
            return in_progress[0], unit_index

        # (2) select the next unit that is uncoded by me
        coded = {t[0] for t in Annotation.select(Unit.id).join(Unit).
            filter(Unit.codingjob == job.id,
                   Annotation.coder == coder.id).tuples()}
        uncoded = list(
            Unit.select()
            .where(Unit.codingjob == job.id, Unit.id.not_in(coded))
            .group_by(Unit.id)
            .limit(1))

        if uncoded:
            return uncoded[0], unit_index

        return None, unit_index

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        if index >= self.n_total(job, coder):
            return None

        if not self.can_seek_forwards or not self.can_seek_backwards:
            coded = sorted(Annotation.select(Annotation.id, Unit.id).join(Unit)
                           .filter(Unit.codingjob == job.id, Annotation.coder == coder.id)
                           .tuples())

            if self.can_seek_forwards == False & index >= len(coded):
                return None
            if self.can_seek_backwards == False & index < len(coded): 
                return None
            return Unit.get_by_id(coded[index][1])
        else:
            units = Unit.select().where(Unit.codingjob == job.id)
            return units[index]


class CrowdCoding(RuleSet):
    """
    Prioritizes coding the entire set as fast as possible using multiple coders.
    """
    def get_next_unit(self, job: CodingJob, coder: User) -> Tuple[Optional[Unit], int]:
        unit_index = self.n_coded(job, coder)
        if unit_index >= self.n_total(job, coder):
            return None, unit_index

        # (1) Is there a unit currently IN_PROGRESS?
        in_progress = list(
            Unit.select()
            .join(Annotation, JOIN.LEFT_OUTER)
            .where(Unit.codingjob == job.id, Annotation.coder == coder.id, Annotation.status == 'IN_PROGRESS')
            .limit(1).execute())
        if in_progress:
            return in_progress[0], unit_index

        # (2) Is there a unit left that has been coded by no one??
        uncoded = list(
            Unit.select()
            .join(Annotation, JOIN.LEFT_OUTER)
            .where(Unit.codingjob == job.id, Annotation.id.is_null())
            .limit(1).execute())
        if uncoded:
            return uncoded[0], unit_index

        # (3) select a unit that is uncoded by me, and least coded by anyone else
        coded = {t[0] for t in Annotation.select(Unit.id).join(Unit).
            filter(Unit.codingjob == job.id,
                   Annotation.coder == coder.id).tuples()}
        least_coded = list(
            Unit.select()
            .join(Annotation)
            .where(Unit.codingjob == job.id, Unit.id.not_in(coded))
            .group_by(Unit.id)
            .order_by(fn.Count(Annotation.id))
            .limit(1))

        if least_coded:
            return least_coded[0], unit_index

        # No units were selected, so done coding I guess?
        # (should we add a check for whether n_coded == self.n_total(job,coder) ?)
        return None, unit_index

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        if index >= self.n_total(job, coder):
            return None

        coded = sorted(Annotation.select(Annotation.id, Unit.id).join(Unit)
                       .filter(Unit.codingjob == job.id, Annotation.coder == coder.id)
                       .tuples())
        if index >= len(coded):
            return None
        if self.can_seek_backwards == False & index < len(coded): 
                return None
        return Unit.get_by_id(coded[index][1])


def get_ruleset(rules: dict) -> RuleSet:
    ruleset_class = {
        'crowdcoding': CrowdCoding,
        'fixedset': FixedSet,
    }[rules['ruleset']]
    return ruleset_class(rules)


def get_next_unit(job: CodingJob, coder: User) -> Optional[Unit]:
    """Return the next unit to code, or None if coder is done"""
    return get_ruleset(job.rules).get_next_unit(job, coder)


def seek_unit(job: CodingJob, coder: User, index: int) -> Optional[Unit]:
    """Seek a specific unit to code by index"""
    return get_ruleset(job.rules).seek_unit(job, coder, index)


def get_progress_report(job: CodingJob, coder: User) -> dict:
    """Return a progress report dictionary"""
    return get_ruleset(job.rules).get_progress(job, coder)
