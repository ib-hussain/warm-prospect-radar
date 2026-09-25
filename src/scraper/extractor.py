"""Deterministic extraction and conservative merging of optional LLM output."""

from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urlsplit

from src.models import BusinessRecord, ContactPoint, PageSnapshot, SocialPlatform, SocialProfile

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])", re.I)
PHONE_PATTERN = re.compile(r"(?<!\d)(\+?\d[\d ().-]{7,}\d)(?!\d)")
YEAR_PATTERN = re.compile(r"\b(?:founded|established|formed)\D{0,30}((?:18|19|20)\d{2})\b", re.I)
EMPLOYEE_PATTERNS = (
    re.compile(r"(?:number of employees|employees|workforce)\s*[:\-]?\s*([\d,.]+)\+?", re.I),
    re.compile(r"([\d,.]+)\+?\s+(?:employees|people worldwide|team members)", re.I),
)
SOCIAL_HOSTS = {
    "facebook.com": SocialPlatform.FACEBOOK,
    "instagram.com": SocialPlatform.INSTAGRAM,
    "linkedin.com": SocialPlatform.LINKEDIN,
    "twitter.com": SocialPlatform.X,
    "x.com": SocialPlatform.X,
    "youtube.com": SocialPlatform.YOUTUBE,
    "youtu.be": SocialPlatform.YOUTUBE,
    "github.com": SocialPlatform.GITHUB,
    "discord.com": SocialPlatform.DISCORD,
    "discord.gg": SocialPlatform.DISCORD,
    "wa.me": SocialPlatform.WHATSAPP,
}
GICS_RULES = (
    ("10", "Energy", ("oil", "gas", "energy", "petroleum", "coal")),
    ("15", "Materials", ("chemical", "mining", "materials", "steel", "paper")),
    ("20", "Industrials", ("industrial", "aerospace", "defense", "transport", "machinery")),
    ("25", "Consumer Discretionary", ("automotive", "retail", "hotel", "restaurant", "consumer")),
    ("30", "Consumer Staples", ("food", "beverage", "household", "tobacco", "grocery")),
    ("35", "Health Care", ("health", "pharma", "biotech", "medical", "hospital")),
    ("40", "Financials", ("bank", "finance", "insurance", "capital markets", "investment")),
    ("45", "Information Technology", ("software", "technology", "semiconductor", "computer", "it services")),
    ("50", "Communication Services", ("telecom", "media", "entertainment", "interactive")),
    ("55", "Utilities", ("utility", "electricity", "water", "renewable")),
    ("60", "Real Estate", ("real estate", "reit", "property")),
)
TECHNOLOGY_TERMS = (
    "AWS",
    "Azure",
    "Google Cloud",
    "Python",
    "Java",
    "React",
    "Salesforce",
    "SAP",
    "Oracle",
    "Kubernetes",
    "Docker",
    "Artificial intelligence",
    "Machine learning",
)


def _dedupe(items: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def _candidate_name(pages: list[PageSnapshot], fallback: str | None) -> str:
    if fallback and fallback.strip():
        return fallback.strip()
    for page in pages:
        organization = page.metadata.get("organization", {})
        if isinstance(organization, dict) and organization.get("name"):
            return str(organization["name"]).strip()[:160]
    for page in pages:
        if page.title:
            title = re.split(r"\s+[|–—-]\s+", page.title, maxsplit=1)[0].strip()
            title = re.sub(r"\s*[-–—]\s*Wikipedia\s*$", "", title, flags=re.I)
            if 1 < len(title) < 120:
                return title
    host = urlsplit(pages[0].final_url).hostname if pages else None
    return (host or "Unknown business").removeprefix("www.").split(".")[0].title()


def _description(pages: list[PageSnapshot]) -> str | None:
    priority = sorted(pages, key=lambda page: ("about" not in page.final_url.lower(), page.depth))
    for page in priority:
        organization = page.metadata.get("organization", {})
        if isinstance(organization, dict) and organization.get("description"):
            return str(organization["description"]).strip()[:1000]
    for page in priority:
        if page.description and len(page.description) >= 40:
            return page.description[:1000]
    for page in priority:
        paragraphs = [part.strip() for part in page.text.splitlines() if len(part.strip()) >= 80]
        if paragraphs:
            return paragraphs[0][:1000]
    return None


def _employees(text: str) -> int | None:
    for pattern in EMPLOYEE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            number = int(float(match.group(1).replace(",", "")))
            if 0 < number < 20_000_000:
                return number
        except ValueError:
            continue
    return None


def _number(value: object) -> int | None:
    if isinstance(value, dict):
        value = value.get("value") or value.get("maxValue") or value.get("minValue")
    if isinstance(value, (int, float)):
        return int(value) if 0 < value < 20_000_000 else None
    if value is None:
        return None
    match = re.search(r"([\d,.]+)", str(value))
    if not match:
        return None
    try:
        parsed = int(float(match.group(1).replace(",", "")))
    except ValueError:
        return None
    return parsed if 0 < parsed < 20_000_000 else None


def _structured_fields(pages: list[PageSnapshot]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for page in pages:
        organization = page.metadata.get("organization", {})
        if isinstance(organization, dict):
            mapping = {
                "legalName": "legal_name",
                "foundingDate": "founded",
                "numberOfEmployees": "employees",
                "address": "address",
                "keywords": "keywords",
            }
            for source, target in mapping.items():
                if target not in fields and organization.get(source) not in (None, ""):
                    fields[target] = organization[source]
        infobox = page.metadata.get("infobox", {})
        if isinstance(infobox, dict):
            for key, target in (
                ("founded", "founded"),
                ("number of employees", "employees"),
                ("headquarters", "headquarters"),
                ("industry", "industry"),
                ("products", "products"),
                ("services", "services"),
            ):
                if target not in fields and infobox.get(key):
                    fields[target] = infobox[key]
    return fields


def _split_terms(value: object) -> list[str]:
    if isinstance(value, list):
        return _dedupe(str(item) for item in value)[:30]
    if not value:
        return []
    return _dedupe(
        item.strip(" ·•")
        for item in re.split(r"\s*[;,·•|]\s*|\s{2,}", str(value))
        if 1 < len(item.strip()) < 100
    )[:30]


def _employee_band(count: int | None) -> str | None:
    if count is None:
        return None
    bounds = (
        (2, "1"),
        (10, "2-9"),
        (50, "10-49"),
        (200, "50-199"),
        (500, "200-499"),
        (1000, "500-999"),
        (5000, "1,000-4,999"),
        (10_000, "5,000-9,999"),
        (50_000, "10,000-49,999"),
    )
    for bound, label in bounds:
        if count < bound:
            return label
    return "50,000+"


def _gics(text: str) -> tuple[str | None, str | None]:
    lowered = text.casefold()
    ranked = []
    for code, sector, keywords in GICS_RULES:
        hits = sum(lowered.count(keyword.casefold()) for keyword in keywords)
        if hits:
            ranked.append((hits, code, sector))
    if not ranked:
        return None, None
    _, code, sector = max(ranked)
    return code, sector


def _social_profiles(pages: list[PageSnapshot]) -> list[SocialProfile]:
    output: list[SocialProfile] = []
    seen: set[tuple[SocialPlatform, str]] = set()
    for page in pages:
        for link in page.links:
            host = (urlsplit(link).hostname or "").removeprefix("www.").lower()
            platform = next((value for key, value in SOCIAL_HOSTS.items() if host == key or host.endswith(f".{key}")), None)
            if not platform:
                continue
            clean = link.split("?", 1)[0].rstrip("/")
            key = (platform, clean.casefold())
            if key in seen:
                continue
            seen.add(key)
            handle = urlsplit(clean).path.strip("/").split("/")[-1] or None
            output.append(
                SocialProfile(
                    platform=platform,
                    url=clean,
                    handle=handle,
                    source_url=page.final_url,
                    confidence=0.8,
                )
            )
    return output


def deterministic_extract(
    pages: list[PageSnapshot], fallback_name: str | None = None
) -> BusinessRecord:
    successful = [page for page in pages if page.text]
    if not successful:
        raise ValueError("No successfully acquired page contained extractable text.")
    combined = "\n".join(page.text for page in successful)
    emails = _dedupe(match.group(1) for match in EMAIL_PATTERN.finditer(combined))[:20]
    phones = _dedupe(re.sub(r"\s+", " ", match.group(1)) for match in PHONE_PATTERN.finditer(combined))[:20]
    contacts = [ContactPoint(kind="email", value=email, confidence=0.9) for email in emails]
    contacts.extend(ContactPoint(kind="phone", value=phone, confidence=0.65) for phone in phones)
    founded = YEAR_PATTERN.search(combined)
    structured = _structured_fields(successful)
    structured_founded = re.search(r"((?:18|19|20)\d{2})", str(structured.get("founded", "")))
    employees = _number(structured.get("employees")) or _employees(combined)
    classification_text = f"{structured.get('industry', '')}\n{combined}"
    gics_code, gics_sector = _gics(classification_text)
    technologies = [term for term in TECHNOLOGY_TERMS if term.casefold() in combined.casefold()]
    source_urls = _dedupe(page.final_url for page in successful)
    official_websites = [
        str(page.metadata["official_website"])
        for page in successful
        if page.metadata.get("official_website")
    ]
    organization_websites = [
        str(organization["url"])
        for page in successful
        if isinstance((organization := page.metadata.get("organization", {})), dict)
        and organization.get("url")
    ]
    website = (official_websites or organization_websites or source_urls or [None])[0]
    products_services = _split_terms(structured.get("products"))
    products_services.extend(_split_terms(structured.get("services")))
    keywords: list[str] = []
    keywords.extend(_split_terms(structured.get("keywords")))
    for page in successful:
        keywords.extend(_split_terms(page.metadata.get("keywords")))

    return BusinessRecord(
        name=_candidate_name(successful, fallback_name),
        legal_name=str(structured["legal_name"])[:200] if structured.get("legal_name") else None,
        description=_description(successful),
        website=website,
        founded_year=int((structured_founded or founded).group(1)) if (structured_founded or founded) else None,
        employee_count=employees,
        employee_band=_employee_band(employees),
        gics_sector_code=gics_code,
        gics_sector=gics_sector,
        products_services=_dedupe(products_services),
        technologies=technologies,
        keywords=_dedupe(keywords),
        contacts=contacts,
        social_profiles=_social_profiles(successful),
        source_urls=source_urls,
    )


def merge_llm_data(business: BusinessRecord, llm_data: dict[str, object]) -> BusinessRecord:
    """Fill gaps without letting lower-confidence model output erase observed data."""
    scalar_fields = (
        "legal_name",
        "description",
        "city",
        "region",
        "country_code",
        "founded_year",
        "employee_count",
        "employee_band",
        "gics_sector_code",
        "gics_sector",
        "gics_industry_group_code",
        "gics_industry_group",
        "gics_industry_code",
        "gics_industry",
        "gics_sub_industry_code",
        "gics_sub_industry",
    )
    for field in scalar_fields:
        if getattr(business, field) in (None, "") and llm_data.get(field) not in (None, ""):
            try:
                setattr(business, field, llm_data[field])
            except (TypeError, ValueError):
                continue
    for field in ("products_services", "technologies", "keywords"):
        incoming = llm_data.get(field)
        if isinstance(incoming, list):
            setattr(business, field, _dedupe([*getattr(business, field), *(str(item) for item in incoming)])[:30])
    business.employee_band = business.employee_band or _employee_band(business.employee_count)
    return business
