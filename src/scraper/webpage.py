"""Resilient, polite, same-site web crawler with optional JavaScript rendering."""

from __future__ import annotations

import ipaddress
import json
import random
import re
import socket
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from src.config import Settings
from src.models import PageSnapshot

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
TRACKING_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_")
NON_HTML_SUFFIXES = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".svg",
    ".tar",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}


class ScrapeError(RuntimeError):
    pass


def normalize_url(raw_url: str, base_url: str | None = None) -> str:
    candidate = raw_url.strip()
    if base_url:
        candidate = urljoin(base_url, candidate)
    elif "://" not in candidate:
        candidate = f"https://{candidate}"
    parts = urlsplit(candidate)
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError(f"Only absolute HTTP(S) URLs are supported: {raw_url!r}")
    host = parts.hostname.lower().rstrip(".")
    port = parts.port
    netloc = host
    if port and not (
        (parts.scheme == "http" and port == 80) or (parts.scheme == "https" and port == 443)
    ):
        netloc = f"{host}:{port}"
    clean_query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_QUERY_PREFIXES)
    ]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), netloc, path, urlencode(clean_query), ""))


def _same_site(candidate: str, seed: str) -> bool:
    candidate_host = (urlsplit(candidate).hostname or "").removeprefix("www.")
    seed_host = (urlsplit(seed).hostname or "").removeprefix("www.")
    return candidate_host == seed_host


def _is_html_candidate(url: str) -> bool:
    path = urlsplit(url).path.lower()
    return not any(path.endswith(suffix) for suffix in NON_HTML_SUFFIXES)


def _priority(url: str) -> int:
    path = urlsplit(url).path.lower()
    if any(token in path for token in ("about", "company", "who-we-are", "our-story")):
        return 0
    if any(token in path for token in ("contact", "team", "leadership", "management")):
        return 1
    if any(token in path for token in ("service", "product", "solution", "what-we-do")):
        return 2
    if any(token in path for token in ("news", "press", "blog", "investor")):
        return 3
    if any(token in path for token in ("privacy", "terms", "cookie", "login", "signup", "cart")):
        return 9
    return 5


def _public_host(url: str) -> bool:
    hostname = urlsplit(url).hostname
    if not hostname:
        return False
    if hostname.lower() == "localhost":
        return False
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ScrapeError(f"Could not resolve host {hostname}: {exc}") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            return False
    return True


@dataclass(slots=True)
class FetchResult:
    html: str
    final_url: str
    status_code: int
    content_type: str
    renderer: str
    warnings: list[str]


class WebScraper:
    def __init__(self, url: str, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.url = normalize_url(url)
        self.client = httpx.Client(
            headers={
                "User-Agent": self.settings.scraper_user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.8",
            },
            timeout=self.settings.scraper_timeout_seconds,
            follow_redirects=False,
            verify=self.settings.scraper_verify_tls,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        self._robots: dict[str, RobotFileParser | None] = {}

    def __enter__(self) -> WebScraper:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def _robot_parser(self, url: str) -> RobotFileParser | None:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root in self._robots:
            return self._robots[root]
        parser = RobotFileParser()
        parser.set_url(f"{root}/robots.txt")
        try:
            response = self.client.get(parser.url)
            if response.status_code < 400:
                parser.parse(response.text.splitlines())
                self._robots[root] = parser
            else:
                self._robots[root] = None
        except httpx.HTTPError:
            self._robots[root] = None
        return self._robots[root]

    def _allowed(self, url: str) -> bool:
        if not self.settings.scraper_respect_robots:
            return True
        parser = self._robot_parser(url)
        return parser is None or parser.can_fetch(self.settings.scraper_user_agent, url)

    def _http_fetch(self, url: str, attempts: int = 3) -> FetchResult:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                target = url
                for _redirect in range(9):
                    response = self.client.get(target)
                    if response.status_code not in {301, 302, 303, 307, 308}:
                        break
                    location = response.headers.get("location")
                    if not location:
                        break
                    target = normalize_url(location, target)
                    if not _public_host(target):
                        raise ScrapeError(
                            "A redirect targeted a private, reserved, or local address."
                        )
                    if not self._allowed(target):
                        raise ScrapeError(f"robots.txt does not permit redirected target {target}")
                else:
                    raise ScrapeError(f"Too many redirects while acquiring {url}")
                if response.status_code in RETRYABLE_STATUS and attempt + 1 < attempts:
                    retry_after = response.headers.get("retry-after", "")
                    delay = (
                        min(10.0, float(retry_after))
                        if retry_after.isdigit()
                        else 0.6 * (2**attempt)
                    )
                    time.sleep(delay + random.uniform(0, 0.2))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type and not any(
                    token in content_type for token in ("html", "xhtml", "text/plain")
                ):
                    raise ScrapeError(f"Unsupported content type {content_type} at {url}")
                return FetchResult(
                    html=response.text,
                    final_url=normalize_url(str(response.url)),
                    status_code=response.status_code,
                    content_type=content_type or "text/html",
                    renderer="http",
                    warnings=[],
                )
            except (httpx.HTTPError, ScrapeError) as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(0.5 * (2**attempt) + random.uniform(0, 0.2))
        raise ScrapeError(f"HTTP acquisition failed for {url}: {last_error}") from last_error

    def _playwright_fetch(self, url: str) -> FetchResult:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ScrapeError("Playwright is not installed.") from exc
        try:
            with sync_playwright() as playwright:
                launch_options: dict[str, object] = {"headless": True}
                if self.settings.playwright_executable_path:
                    launch_options["executable_path"] = self.settings.playwright_executable_path
                browser = playwright.chromium.launch(**launch_options)
                page = browser.new_page(user_agent=self.settings.scraper_user_agent)
                host_safety: dict[str, bool] = {}

                def guard_request(route: object, request: object) -> None:
                    request_url = str(getattr(request, "url", ""))
                    scheme = urlsplit(request_url).scheme.lower()
                    if scheme in {"about", "blob", "data"}:
                        route.continue_()
                        return
                    try:
                        normalized = normalize_url(request_url)
                        host = urlsplit(normalized).hostname or ""
                        if host not in host_safety:
                            host_safety[host] = _public_host(normalized)
                        allowed = host_safety[host]
                    except (ValueError, ScrapeError):
                        allowed = False
                    if allowed:
                        route.continue_()
                    else:
                        route.abort("blockedbyclient")

                page.route("**/*", guard_request)
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(self.settings.scraper_timeout_seconds * 1000),
                )
                page.wait_for_timeout(700)
                html = page.content()
                final_url = normalize_url(page.url)
                if not _public_host(final_url):
                    raise ScrapeError(
                        "JavaScript rendering redirected to a private, reserved, or local address."
                    )
                status = response.status if response else 200
                browser.close()
            return FetchResult(
                html=html,
                final_url=final_url,
                status_code=status,
                content_type="text/html",
                renderer="playwright",
                warnings=["HTTP page was sparse; JavaScript rendering fallback was used."],
            )
        except Exception as exc:
            raise ScrapeError(f"JavaScript rendering failed for {url}: {exc}") from exc

    @staticmethod
    def _looks_javascript_dependent(html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        visible = soup.get_text(" ", strip=True)
        script_count = len(soup.find_all("script"))
        markers = ("enable javascript", "javascript is required", "__next_data__", 'id="root"')
        return len(visible) < 240 and (
            script_count >= 3 or any(marker in html.lower() for marker in markers)
        )

    def fetch(self, url: str) -> FetchResult:
        if not _public_host(url):
            raise ScrapeError(
                "The target resolves to a private, reserved, or local network address."
            )
        if not self._allowed(url):
            raise ScrapeError(f"robots.txt does not permit acquisition of {url}")
        result = self._http_fetch(url)
        if self.settings.scraper_js_fallback and self._looks_javascript_dependent(result.html):
            try:
                return self._playwright_fetch(url)
            except ScrapeError as exc:
                result.warnings.append(str(exc))
        return result

    @staticmethod
    def _parse(result: FetchResult, depth: int) -> PageSnapshot:
        soup = BeautifulSoup(result.html, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else None
        description_tag = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if not description_tag:
            description_tag = soup.find("meta", attrs={"property": "og:description"})
        description = description_tag.get("content", "").strip() if description_tag else None

        metadata: dict[str, object] = {}
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        if canonical and canonical.get("href"):
            try:
                metadata["canonical_url"] = normalize_url(canonical["href"], result.final_url)
            except ValueError:
                pass
        site_name = soup.find("meta", attrs={"property": "og:site_name"})
        if site_name and site_name.get("content"):
            metadata["site_name"] = site_name["content"].strip()
        keywords = soup.find("meta", attrs={"name": re.compile("^keywords$", re.I)})
        if keywords and keywords.get("content"):
            metadata["keywords"] = [
                item.strip() for item in keywords["content"].split(",") if item.strip()
            ][:30]

        organization: dict[str, object] | None = None
        for script in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
            raw = script.string or script.get_text(strip=True)
            if not raw:
                continue
            try:
                document = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            pending = document if isinstance(document, list) else [document]
            expanded: list[object] = []
            for item in pending:
                if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)
            for item in expanded:
                if not isinstance(item, dict):
                    continue
                raw_type = item.get("@type", "")
                types = raw_type if isinstance(raw_type, list) else [raw_type]
                if any(
                    str(value).casefold()
                    in {"organization", "corporation", "localbusiness", "company"}
                    for value in types
                ):
                    allowed = {
                        "name",
                        "legalName",
                        "url",
                        "description",
                        "foundingDate",
                        "numberOfEmployees",
                        "address",
                        "email",
                        "telephone",
                        "sameAs",
                        "keywords",
                    }
                    organization = {key: item[key] for key in allowed if key in item}
                    break
            if organization:
                break
        if organization:
            metadata["organization"] = organization

        infobox: dict[str, str] = {}
        official_website: str | None = None
        for row in soup.select("table.infobox tr"):
            heading, value = row.find("th"), row.find("td")
            if not heading or not value:
                continue
            key = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)).strip().casefold()
            text_value = re.sub(r"\s+", " ", value.get_text(" ", strip=True)).strip()
            if key and text_value:
                infobox[key] = text_value[:1000]
            if key == "website":
                anchor = value.find("a", href=True)
                if anchor:
                    try:
                        official_website = normalize_url(anchor["href"], result.final_url)
                    except ValueError:
                        pass
        if infobox:
            metadata["infobox"] = infobox
        if official_website:
            metadata["official_website"] = official_website

        links: list[str] = []
        seen_links: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            try:
                link = normalize_url(unescape(anchor["href"]), result.final_url)
            except (ValueError, TypeError):
                continue
            if link not in seen_links:
                seen_links.add(link)
                links.append(link)
        if organization:
            same_as = organization.get("sameAs", [])
            if isinstance(same_as, str):
                same_as = [same_as]
            if isinstance(same_as, list):
                for raw_link in same_as:
                    try:
                        link = normalize_url(str(raw_link), result.final_url)
                    except ValueError:
                        continue
                    if link not in seen_links:
                        seen_links.add(link)
                        links.append(link)

        for node in soup(["script", "style", "svg", "template", "noscript"]):
            node.decompose()
        text = re.sub(r"[ \t]+", " ", soup.get_text("\n", strip=True))
        text = re.sub(r"\n{3,}", "\n\n", text)
        return PageSnapshot(
            url=result.final_url,
            final_url=result.final_url,
            title=title,
            description=description,
            text=text[:150_000],
            raw_html=result.html,
            status_code=result.status_code,
            content_type=result.content_type,
            depth=depth,
            renderer=result.renderer,
            links=links,
            metadata=metadata,
            warnings=result.warnings,
        )

    def scrape(
        self,
        max_pages: int | None = None,
        max_depth: int | None = None,
    ) -> list[PageSnapshot]:
        page_limit = max_pages or self.settings.scraper_max_pages
        depth_limit = self.settings.scraper_max_depth if max_depth is None else max_depth
        queue: deque[tuple[int, int, str]] = deque([(5, 0, self.url)])
        queued = {self.url}
        visited: set[str] = set()
        pages: list[PageSnapshot] = []

        while queue and len(pages) < page_limit:
            ordered = sorted(queue, key=lambda item: (item[0], item[1], item[2]))
            queue = deque(ordered)
            _, depth, target = queue.popleft()
            if target in visited:
                continue
            visited.add(target)
            try:
                result = self.fetch(target)
                page = self._parse(result, depth)
                pages.append(page)
            except ScrapeError as exc:
                pages.append(
                    PageSnapshot(
                        url=target,
                        final_url=target,
                        depth=depth,
                        warnings=[str(exc)],
                    )
                )
                continue

            if depth >= depth_limit:
                continue
            candidates: list[tuple[int, int, str]] = []
            for link in page.links:
                if (
                    link in visited
                    or link in queued
                    or not _same_site(link, self.url)
                    or not _is_html_candidate(link)
                ):
                    continue
                queued.add(link)
                candidates.append((_priority(link), depth + 1, link))
            queue.extend(sorted(candidates))
            if self.settings.scraper_delay_seconds:
                time.sleep(self.settings.scraper_delay_seconds)
        return pages

    def return_json(self, path: Path) -> Path:
        """Compatibility helper: crawl and write page records to a JSON file."""
        import json

        pages = self.scrape()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps([page.model_dump(mode="json") for page in pages], indent=2),
            encoding="utf-8",
        )
        return path


def successful_pages(pages: Iterable[PageSnapshot]) -> list[PageSnapshot]:
    return [page for page in pages if page.status_code and page.text]
