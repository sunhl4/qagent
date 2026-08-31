from __future__ import annotations

from qagent.adapters.contracts import load_company
from qagent.models.company import CompanyProfile, MatrixItem
from qagent.services.engines import list_engines, list_reserved_engines


def company_profile() -> CompanyProfile:
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


def company_payload() -> dict:
    profile = company_profile()
    return {
        "company": {
            "legal_name": profile.legal_name,
            "short_name": profile.short_name,
            "english_name": profile.english_name,
            "product": profile.product,
            "slogan": profile.slogan,
            "tagline": profile.tagline,
            "city": profile.city,
            "site": profile.site,
        },
        "matrix": [item.__dict__ for item in profile.matrix],
        "engines": [
            {
                "id": pack.id,
                "kind": pack.kind,
                "label": pack.label,
                "status": pack.status,
                "tools": pack.tools,
                "identity_fields": pack.identity_fields,
                "vibe": pack.vibe,
            }
            for pack in list_engines()
        ],
        "reserved_engines": [
            {
                "id": pack.id,
                "kind": pack.kind,
                "label": pack.label,
                "status": pack.status,
                "tools": pack.tools,
                "identity_fields": pack.identity_fields,
                "vibe": pack.vibe,
            }
            for pack in list_reserved_engines()
        ],
        "handles": ["circuit_id", "asset_id", "twin_id"],
    }
