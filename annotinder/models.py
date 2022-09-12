import json
from sqlalchemy import func, Boolean, Column, ForeignKey, Integer, String, Float, DateTime, ForeignKeyConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship

from annotinder.database import Base


class JsonString(TypeDecorator):
    """Enables JSON storage by encoding and decoding on the fly."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class User(Base):
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, index=True)
    is_admin = Column(Boolean, default=False)
    restricted_job = Column(Integer, nullable=True)
    password = Column(String, nullable=True)

    codingjobs = relationship("CodingJob", back_populates="creator")


class CodingJob(Base):
    __tablename__ = 'codingjob'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    creator_id = Column(Integer, ForeignKey("user.id"))
    title = Column(String)
    provenance = Column(JsonString, nullable=True)
    restricted = Column(Boolean, default=False)
    created = Column(DateTime(timezone=True), server_default=func.now())
    archived = Column(Boolean, default=False)

    creator = relationship("User", back_populates="codingjobs")
    jobsets = relationship("JobSet", back_populates="codingjob")
    jobusers = relationship("JobUser", back_populates="codingjob")


class JobSet(Base):
    __tablename__ = 'jobset'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codingjob_id = Column(Integer, ForeignKey("codingjob.id"), index=True)
    jobset = Column(String)
    codebook = Column(JsonString)
    rules = Column(JsonString)
    debriefing = Column(JsonString, nullable=True)

    codingjob = relationship("CodingJob", back_populates="jobsets")
    jobsetunits = relationship('JobSetUnit')
    jobusers = relationship("JobUser", back_populates="jobset")



class Unit(Base):
    __tablename__ = 'unit'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codingjob_id = Column(Integer, ForeignKey("codingjob.id"), index=True)
    external_id = Column(String, index=True)
    unit = Column(JsonString, nullable=True)
    conditionals = Column(JsonString, nullable=True)
    unit_type = Column(String)
    position = Column(String)

    annotation = relationship("Annotation", back_populates='unit')


class JobSetUnit(Base):
    __tablename__ = 'jobsetunit'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    jobset_id = Column(Integer, ForeignKey("jobset.id"), index=True)
    unit_id = Column(Integer, ForeignKey("unit.id"), index=True)
    fixed_index = Column(Integer, default=None, index=True)
    unit_type = Column(String, index=True)
    has_conditionals = Column(Boolean, default=False)
    blocked = Column(Boolean, default=False) # block a unit from new assignments (e.g., coded enough, marked as irrelevant)


class JobUser(Base):
    __tablename__ = 'jobuser'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('user.id'), index=True)
    codingjob_id = Column(Integer, ForeignKey('codingjob.id'), index=True)
    jobset_id = Column(Integer, ForeignKey('jobset.id'), index=True)
    can_code = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    damage = Column(Float, default=0)
    status = Column(String, default='active')
    
    ForeignKeyConstraint(['user_id', 'codingjob_id'], [
                         'user.id', 'codingjob.id'])
    codingjob = relationship('CodingJob', back_populates="jobusers")
    jobset = relationship("JobSet", back_populates="jobusers")




class Annotation(Base):
    __tablename__ = 'annotation'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    codingjob_id = Column(Integer, ForeignKey('codingjob.id'), index=True)
    unit_id = Column(Integer, ForeignKey('unit.id'), index=True)
    coder_id = Column(Integer, ForeignKey('user.id'), index=True)
    jobset_id = Column(Integer, ForeignKey('jobset.id'), index=True)
    unit_index = Column(Integer, index=True) # coder specific unit_index (needed for serve_unit)
    status = Column(String, index=True)
    modified = Column(DateTime(timezone=True), server_default=func.now())
    annotation = Column(JsonString)
    report = Column(JsonString, nullable=True)

    damage = Column(Float, default=0)

    unit = relationship('Unit', back_populates='annotation')
