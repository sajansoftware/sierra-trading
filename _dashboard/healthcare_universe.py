"""Health Care sector — proxy module that unifies the biotech and
healthcare-services universes under a single Health Care namespace
(matches the GICS top-level sector taxonomy)."""

from __future__ import annotations

import universe as _bio
import healthcare_svc_universe as _svc


# Sub-sector folder constants — combined biotech (7-color) + healthcare-services
# folders under the single Health Care industry.
FOLDERS = _bio.FOLDERS + _svc.FOLDERS


INFO = {**_bio.INFO, **_svc.INFO}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for k, v in _bio.UNIVERSE().items():
        out[k] = list(v)
    for k, v in _svc.UNIVERSE().items():
        out[k] = list(v)
    return out


def all_tickers() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for syms in UNIVERSE().values():
        for s in syms:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out
