import json
from sqlalchemy import func, Boolean, Column, ForeignKey, Integer, String, JSON, DateTime, ForeignKeyConstraint
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import relationship

from amcat4annotator.database import Base

class JsonString(TypeDecorator):
    """Enables JSON storage by encoding and decoding on the fly."""

    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return json.loads(value)


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String, index=True)
    is_admin = Column(Boolean, default=False)
    restricted_job = Column(Integer, nullable=True)
    password = Column(String, nullable=True)

    codingjobs = relationship("CodingJob", back_populates="creator")




class CodingJob(Base):
    __tablename__ = 'codingjobs'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)    
    creator_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String)
    provenance = Column(JsonString, nullable=True)
    rules = Column(JsonString, nullable=True)
    debriefing = Column(JsonString, nullable=True)
    restricted = Column(Boolean, default=False)
    created = Column(DateTime(timezone=True), server_default=func.now())
    archived = Column(Boolean, default=False)

    creator = relationship("User", back_populates="codingjobs")
    jobsets = relationship("JobSet", back_populates="codingjob")
    jobusers = relationship("JobUser", back_populates="codingjob")


class Unit(Base):
    __tablename__ = 'units'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)    
    codingjob_id = Column(Integer, ForeignKey("codingjobs.id"), index=True)
    external_id = Column(String, index=True)  
    unit = Column(JsonString, nullable=True)
    gold = Column(JsonString, nullable=True)

    annotations = relationship("Annotation", back_populates='unit')

    
class JobSet(Base):
    __tablename__ = 'jobsets'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)    
    codingjob_id = Column(Integer, ForeignKey("codingjobs.id"), index=True)
    jobset = Column(String)  
    codebook = Column(JsonString, nullable=True)
    
    codingjob = relationship("CodingJob", back_populates="jobsets")
    jobsetunits = relationship('JobSetUnits')


class JobSetUnits(Base):
    __tablename__ = 'jobsetunits'
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)      
    jobset_id = Column(Integer, ForeignKey("jobsets.id"), index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), index=True)
  
    

class JobUser(Base):
    __tablename__ = 'jobusers'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)    
    user_id = Column(Integer, ForeignKey('users.id'), index=True)
    codingjob_id = Column(Integer, ForeignKey('codingjobs.id'), index=True)
    jobset = Column(String, nullable=True)
    can_code = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)

    ForeignKeyConstraint(['user_id','codingjob_id'],['users.id','codingjobs.id'])
    codingjob = relationship('CodingJob', back_populates="jobusers")

   


class Annotation(Base):
    __tablename__ = 'annotations'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)    
    unit_id = Column(Integer, ForeignKey('units.id'), index=True)
    coder_id = Column(Integer, ForeignKey('users.id'))
    jobset = Column(String)
    status = Column(String)
    modified = Column(DateTime(timezone=True), server_default=func.now())
    annotation = Column(JsonString)
 
    unit = relationship('Unit', back_populates='annotations')
