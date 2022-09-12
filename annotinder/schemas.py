from typing import List, Dict, Optional
from datetime import datetime
from pydantic import BaseModel

## currently not used



class UserBase(BaseModel):
    name: str
    is_admin: bool = False
    restricted_job: Optional[bool] = None

class UserCreate(UserBase):
    password: str
    
class User(UserBase):
    id: int
    
    class Config:
        orm_mode = True



class CodingjobBase(BaseModel):
    title: str
    provenance: Dict = None
    rules: Dict = None
    debriefing: Dict = None
    restricted: bool = False
    
class CodingjobCreate(CodingjobBase):
    pass

class Codingjob(CodingjobBase):
    id: int
    creator: User
    created: datetime
    archived: bool = False
        
    class Config:
        orm_mode = True


