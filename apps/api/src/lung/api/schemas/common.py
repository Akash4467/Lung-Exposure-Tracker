from datetime import time
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Local wall-clock times travel as "HH:MM".
HHMM = Annotated[time, PlainSerializer(lambda t: t.strftime("%H:%M"), return_type=str)]


class Model(BaseModel):
    """Requests reject unknown fields, so typos fail loudly instead of being ignored."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
