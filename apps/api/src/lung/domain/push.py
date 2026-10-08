from dataclasses import dataclass


@dataclass(frozen=True)
class Push:
    title: str
    body: str
    data: dict[str, str]
