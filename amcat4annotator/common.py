from typing import Iterable, List

import bcrypt

from amcat4annotator.db import CodingJob, Unit


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def get_units(codingjob_id: str) -> Iterable[Unit]:
    return Unit.select().where(Unit.codingjob == codingjob_id)


