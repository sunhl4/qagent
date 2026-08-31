from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatrixItem:
    id: str
    lane: str
    label: str
    status: str
    blurb: str = ""


@dataclass(frozen=True)
class CompanyProfile:
    legal_name: str
    short_name: str
    english_name: str
    product: str
    slogan: str
    tagline: str
    city: str
    site: str
    matrix: list[MatrixItem] = field(default_factory=list)
