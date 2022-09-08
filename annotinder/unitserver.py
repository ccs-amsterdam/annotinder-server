from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from annotinder.models import Unit, User, Annotation, CodingJob, JobSetUnit, JobSet, JobUser
from annotinder.crud import crud_codingjob
from annotinder.utils import random_indices


class ValidationError(Exception):
    pass


class UnitServer:
    """
    A class for determining what units to serve. 
    
    The business logic is determined by a Rule set:
    - How should units be distributed over coders
    - Is coding limited to specific coders?
    - Can coders scroll backwards/forwards
    - What Q/A measures are in place?
    """

    def __init__(self, db: Session, jobuser: JobUser, jobset: JobSet):
        self.db = db
        self.jobuser = jobuser
        self.jobset = jobset

    def get_progress(self) -> dict:
        """
        Return the progress report for this job, including seek permissions
        """
        # eventually, might need to deal with jobsets if we decide that coders can do multiple jobsets
        # per codingjob. But maybe we should not encourage this, and instead focus on use cases where one
        # might think this would be wise. The only case I can think of is having a coder do more units
        # beyond the set, but then there should be better ways that doing other (partially overlapping) sets.

        last_modified = self.db.query(Annotation.modified, func.max(Annotation.modified)).filter(Annotation.coder_id == self.jobuser.user_id, Annotation.jobset_id == self.jobset.id).first()
        progress = dict(
            n_total=self.n_total(),
            n_coded=self.coded().count(),
            seek_backwards=self.can_seek_backwards,
            seek_forwards=self.can_seek_forwards,
            last_modified = last_modified.modified
        )
        
        damage = self.damage()
        if self.jobset.rules.get('show_damage', False):
            progress['damage'] = damage['damage']
            progress['max_damage'] = damage['max_damage']
            progress['damage'] = damage['game_over']
        
        return progress

    def damage(self):
        """
        See current damage status
        """
        damage = self.jobuser.damage
        max_damage = self.jobset.rules.get('max_damage')
        game_over = max_damage is not None and damage >= max_damage 
        return dict(damage=damage, max_damage=max_damage, game_over=game_over)
        

    def seek_unit(self, index: int) -> Optional[Unit]:
        """
        Get a specific unit by index. Note that this index is specific for a CodingJob X User. 
        The first item in a CodingJob or user 1 is not necesarily the same as for user 2.  
        Returns two values. First is the Unit, which can be None if missing. Second is the unit index,
        because in some cases the input index can be overruled
        """
        raise NotImplementedError()

    def get_next_unit(self) -> Tuple[Optional[Unit], int]:
        """
        Like seek_unit, but without specifying an index. The next unit will then be determined
        by some rule specific method (e.g., order in DB, prioritizing units least coded by others).
        Returns two values. First is the Unit, which can be None if missing. Second is the unit index. 
        """
        raise NotImplementedError()

    def get_unit_with_status(self, statuses: List[str]):
        """
        get first unit with a particular status
        """
        ann = self.db.query(Annotation.unit_id, Annotation.unit_index).join(JobSet).filter(
            JobSet.codingjob_id == self.jobset.codingjob_id, Annotation.coder_id == self.jobuser.user_id, Annotation.status.in_(statuses)).first()
        if ann:
            return self.db.query(Unit).filter(Unit.id == ann.unit_id).first(), ann.unit_index
        return None, None

    def get_started_unit(self, index: int):
        """
        Get a unit that has already been started by its index. 
        Can only get units before the current unit if can_seek_backwards is True.
        """
        ann = self.db.query(Annotation.unit_id, Annotation.unit_index).join(JobSet).filter(
            JobSet.codingjob_id == self.jobset.codingjob_id, Annotation.coder_id == self.jobuser.user_id, Annotation.unit_index == index).first()
        if ann is None:
            return None

        max_index = self.started().count() - 1
        if index < max_index and not self.can_seek_backwards:
            return None
        return self.db.query(Unit).filter(Unit.id == ann.unit_id).first()

    def get_fixed_index_unit(self, unit_index: int):
        """
        Check if the current unit_index matches a unit with a fixed unit index (e.g., pre and post units).
        Checks both the exact index and negative index (-1 means show this unit last)
        """
        unit = self.db.query(Unit).join(JobSetUnit).filter(JobSetUnit.jobset_id == self.jobset.id, JobSetUnit.fixed_index == unit_index).first()
        if not unit:
            n = self.n_total()
            unit = self.db.query(Unit).join(JobSetUnit).filter(JobSetUnit.jobset_id == self.jobset.id, JobSetUnit.fixed_index == (unit_index-n)).first()
        return unit


    @property
    def can_seek_backwards(self):
        if 'can_seek_backwards' in self.jobset.rules:
            return self.jobset.rules['can_seek_backwards']
        return True

    @property
    def can_seek_forwards(self):
        if 'can_seek_forwards' in self.jobset.rules:
            return self.jobset.rules['can_seek_forwards']
        return False
        
    def units(self):
        """
        Get all units in a job
        """
        return self.db.query(Unit).join(JobSetUnit).filter(JobSetUnit.jobset_id == self.jobset.id).order_by(JobSetUnit.id)

    def coded(self):
        """
        Get coded units for a given job and user
        """
        return self.db.query(Annotation).join(JobSet).filter(JobSet.codingjob_id == self.jobset.codingjob_id, Annotation.coder_id == self.jobuser.user_id, Annotation.status != 'IN_PROGRESS')

    def started(self):
        """
        Get units that a user has already started in given job. 
        """
        return self.db.query(Annotation).join(JobSet).filter(JobSet.codingjob_id == self.jobset.codingjob_id, Annotation.coder_id == self.jobuser.user_id)

    def n_total(self):
        """
        Total number of units that a user can code.
        This is separate from just unsing self.units().count() because a ruleset might specify an alternative (like units_per_coder in CrowdCoding)
        """
        return self.units().count()

    def count_coders(self, unit: Unit):
        """
        Get total number of coders working on this unit (including IN_PROGRESS). The +1 is for the current coder (which we exclude from the annotations)
        """
        return 1 + self.db.query(Annotation.unit_id).filter(Annotation.coder_id != self.jobuser.user_id, Annotation.unit_id == unit.id, Annotation.jobset_id == self.jobset.id).count()






class FixedSet(UnitServer):
    """
    Each coder receives the units in the same order as loaded into the DB.
    """

    def get_next_unit(self) -> Tuple[Optional[Unit], int]:
        # (1) Is there a unit currently IN_PROGRESS or RETRY?
        unit, unit_index = self.get_unit_with_status(['IN_PROGRESS', 'RETRY'])
        if unit:
            return unit, unit_index

        # (2) select the next unit
        unit_index = self.started().count()
        return self.get_unit(unit_index), unit_index

    def seek_unit(self, index: int) -> Optional[Unit]:
        # (1) If index is invalid, use get_next_unit
        if index < 0 or (index >= self.coded().count() and not self.can_seek_forwards):
            return self.get_next_unit()
        
        # (2) try if index is an already started unit (taking can_seek_backwards into account)
        unit = self.get_started_unit(index)
        if unit is not None:
            return unit, index
        
        # (3) the only other option is seeking forward
        if not self.can_seek_forwards:
            return None, index

        return self.get_unit(index), index

    def n_total(self):
        # If sets are specified, n is set length. Otherwise n is total number of units

        # We call units with assign_set = False to prevent that the user is assigned
        # to a set if they only viewed the number of items in the job. Note that this also means
        # that a coder might see that a job has x number of units, but if they start the number
        # might be different if in the meantime another coder started the job (and number of items per set are different)
        units = self.units()
        return units.count()

    def get_unit(self, index: int):
        units = self.units()
        if index < 0 or index >= units.count():
            return None
        if 'randomize' in self.jobset.rules:
            # randomize using coder id as seed, so that each coder has a unique and fixed order
            random_mapping = random_indices(self.jobuser.id, units.count())
            index = random_mapping[index]
        return units[index]


class CrowdCoding(UnitServer):
    """
    The order of units depends on which units have been coded by others.
    Positional units (pre/post) will still have fixed positions. 
    """

    def get_next_unit(self) -> Tuple[Optional[Unit], int]:
        # (1) Is there a unit currently IN_PROGRESS or RETRY?
        unit, unit_index = self.get_unit_with_status(['IN_PROGRESS', 'RETRY'])
        if unit:
            return unit, unit_index

        unit_index = self.started().count()

        if unit_index >= self.n_total():
            return None, unit_index

        # (2) Is there a fixed index unit?
        unit = self.get_fixed_index_unit(unit_index)
        if unit:
            return unit, unit_index

        # (3) select a unit from the jobset that is uncoded by me, and least coded by anyone else in the same jobset
        least_coded = (
            self.db.query(JobSetUnit.unit_id)
            .outerjoin(Annotation, JobSetUnit.unit_id == Annotation.unit_id)
            .filter(JobSetUnit.jobset_id == self.jobset.id, JobSetUnit.blocked == False, or_(Annotation.id == None, Annotation.coder_id != self.jobuser.user_id))
            .group_by(JobSetUnit.unit_id)
            .order_by(func.count(Annotation.id))
            .first()
        )
        if least_coded:
            return self.db.query(Unit).filter(Unit.id == least_coded.unit_id).first(), unit_index

        # No units were left without annotations by the coder, so done coding I guess?
        return None, unit_index

    def seek_unit(self,  index: int) -> Optional[Unit]:
        # (1) If index is invalid, use get_next_unit
        if index < 0 or (index >= self.coded().count()):
            return self.get_next_unit()

        # (2) if index is higher than total number of units, return None and index.
        #     in the client this should direct to the finished page
        if index >= self.n_total():
            return None, index

        # (2) Get unit by index. For crowd coding this can only be units that already started
        #     (seek forward is impossible because the next unit is determined by the crowd)
        return self.get_started_unit(index), index

    def n_total(self):
        """
        For CrowdCoding, the number of units can be limited with the units_per_coder setting.
        Also, units can be blocked (e.g., saturated, marked irrelevant), so we can ran out of units,
        and coders that join later might have a different n_total.
        """
        n_units = self.units().count()

        n_units = (
            self.db.query(JobSetUnit.unit_id)
            .outerjoin(Annotation, JobSetUnit.unit_id == Annotation.unit_id)
            .filter(JobSetUnit.jobset_id == self.jobset.id, or_(JobSetUnit.blocked == False, Annotation.coder_id != self.jobuser.user_id))
            .count()
        )
        if 'units_per_coder' in self.jobset.rules:
            n_units = min(self.jobset.rules['units_per_coder'], n_units)
        return n_units


def get_unitserver(db: Session, jobuser: JobUser) -> UnitServer:
    jobset = jobuser.jobset
    unitserver_class = {
        'crowdcoding': CrowdCoding,
        'fixedset': FixedSet,
    }[jobset.rules['ruleset']]
    return unitserver_class(db, jobuser, jobset)


def serve_unit(db, jobuser: JobUser, index: Optional[int]) -> Optional[Unit]:
    """Serve a unit from a jobset."""
    unitserver = get_unitserver(db, jobuser)
    damage = unitserver.damage()
    if damage['game_over']:
        return None, i
    
    if index is not None:
        index = int(index)
        unit, i = unitserver.seek_unit(index)
    else:
        unit, i = unitserver.get_next_unit()
    return unit, i


def get_progress_report(db, jobset: JobSet) -> dict:
    """Return a progress report dictionary"""
    return get_unitserver(db, jobset).get_progress()
