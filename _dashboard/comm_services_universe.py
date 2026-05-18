"""Communication Services — telecom, media, advertising, publishing, streaming."""

from __future__ import annotations

from dataclasses import dataclass


WIRELESS_WIRELINE_TELECOM = "Wireless_Wireline_Telecom"
SATELLITE_TOWERS          = "Satellite_Towers"
MEDIA_ENTERTAINMENT       = "Media_Entertainment"
ADVERTISING_MARTECH       = "Advertising_MarTech"
SOCIAL_GAMING_PLATFORMS   = "Social_Gaming_Platforms"
PUBLISHING_NEWS           = "Publishing_News"
STREAMING                 = "Streaming"

FOLDERS = (
    WIRELESS_WIRELINE_TELECOM, SATELLITE_TOWERS, MEDIA_ENTERTAINMENT,
    ADVERTISING_MARTECH, SOCIAL_GAMING_PLATFORMS, PUBLISHING_NEWS,
    STREAMING,
)


@dataclass(frozen=True)
class CompanyInfo:
    name: str
    blurb: str
    categories: tuple[str, ...]


INFO: dict[str, CompanyInfo] = {}


def UNIVERSE() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {f: [] for f in FOLDERS}
    for ticker, info in INFO.items():
        for cat in info.categories:
            out[cat].append(ticker)
    try:
        from screener import discover_by_sector, SECTOR_COMMUNICATION
        for sub, syms in discover_by_sector(SECTOR_COMMUNICATION).items():
            if sub not in out:
                continue
            for s in syms:
                if s not in out[sub]:
                    out[sub].append(s)
    except Exception:
        pass
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
