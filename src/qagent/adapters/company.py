from __future__ import annotations

from qagent.adapters.contracts import load_company
from qagent.models.company import CompanyProfile, MatrixItem


def load_company_profile() -> CompanyProfile:
    raw = load_company()
    return CompanyProfile(
        legal_name=raw["legal_name"],
        short_name=raw["short_name"],
        english_name=raw["english_name"],
        product=raw["product"],
        slogan=raw["slogan"],
        tagline=raw["tagline"],
        city=raw["city"],
        site=raw["site"],
        matrix=[
            MatrixItem(
                id=item["id"],
                lane=item["lane"],
                label=item["label"],
                status=item["status"],
                blurb=item.get("blurb", ""),
            )
            for item in raw.get("matrix") or []
        ],
    )
