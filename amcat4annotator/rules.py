from typing import Optional

from peewee import fn, JOIN

from amcat4annotator.db import Unit, User, Annotation, CodingJob


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

    def get_next_unit(self, job: CodingJob, coder: User) -> Optional[Unit]:
        """
        Get the next unit this coder should code. Returns None if no units can be found
        """
        raise NotImplementedError()

    def get_progress(self, job: CodingJob, coder: User) -> dict:
        """
        Return the progress report for this job, including seek permissions
        """
        n_coded = Annotation.select().join(Unit).where(Unit.codingjob == job.id, Annotation.coder == coder.id, Annotation.status != 'IN_PROGRESS').count()
        return dict(
            n_coded=n_coded,
            n_total=self.n_total(job, coder),
            seek_backwards=self.can_seek_backwards,
            seek_forwards=self.can_seek_forwards,
        )

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        """
        Get a specific unit by index. Returns None if index could not be found
        """
        raise NotImplementedError()

    @property
    def can_seek_backwards(self):
        return True

    @property
    def can_seek_forwards(self):
        return False

    def n_total(self, job: CodingJob, coder: User):
        return Unit.select().where(Unit.codingjob == job.id).count()


class CrowdCoding(RuleSet):
    def get_next_unit(self, job: CodingJob, coder: User) -> Optional[Unit]:
        # (1) Is there a unit currently IN_PROGRESS?
        in_progress = list(
            Unit.select()
            .join(Annotation, JOIN.LEFT_OUTER)
            .where(Unit.codingjob == job.id, Annotation.coder == coder.id, Annotation.status == 'IN_PROGRESS')
            .limit(1).execute())
        if in_progress:
            return in_progress[0]

        # (2) Is there a unit left that has been coded by no one??
        uncoded = list(
            Unit.select()
            .join(Annotation, JOIN.LEFT_OUTER)
            .where(Unit.codingjob == job.id, Annotation.id.is_null())
            .limit(1).execute())
        if uncoded:
            return uncoded[0]

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
            return least_coded[0]

        # No units were selected, so done coding I guess?
        return None

    def seek_unit(self, job: CodingJob, coder: User, index: int) -> Optional[Unit]:
        coded = sorted(Annotation.select(Annotation.id, Unit.id).join(Unit)
                       .filter(Unit.codingjob == job.id, Annotation.coder == coder.id)
                       .tuples())
        if index >= len(coded):
            return None
        return Unit.get_by_id(coded[index][1])


def get_ruleset(rules: dict) -> RuleSet:
    ruleset_class = {
        'crowdcoding': CrowdCoding,
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
