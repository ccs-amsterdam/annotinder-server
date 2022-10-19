from msilib.schema import Condition
from typing import List, Dict, Optional, Literal, Union
from datetime import datetime
from pydantic import BaseModel

## currently not used, but should at least specify the _in schemas


class CodingJob(BaseModel):
    units: List[Unit]

class Unit(BaseModel):
    type: Literal["code","train","test","survey"] = "code"
    position: Literal["pre","post"] = None
    id: str
    unit: CodingUnit
    conditionals: Conditionals

class CodingUnit(BaseModel):
    text: str

class Conditionals(BaseModel):
    variable: str
    conditions: Condition
    onSuccess: Literal["applaud"] = None
    onFail: Literal["retry","block"] = None
    damage: float = None
    message: str = None

class Condition(BaseModel):
    value: Union[str, float]
    operator: Literal["==","<=","<",">=",">","!="] = None
    field: str = None
    offset: int = None
    length: int = None
    damage: float = None
    submessage: str = None