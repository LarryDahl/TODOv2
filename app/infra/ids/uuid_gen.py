from __future__ import annotations

import uuid

from app.domain.oppari.ports import IdGenerator


class UuidGenerator(IdGenerator):
    def new_id(self) -> str:
        return str(uuid.uuid4())
