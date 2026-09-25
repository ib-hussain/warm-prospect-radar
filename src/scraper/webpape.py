"""Backward-compatible import for the original misspelled module name.

New code should import :mod:`src.scraper.webpage`. This file is retained so the
requested initial structure and any early imports do not break.
"""

from src.scraper.webpage import ScrapeError, WebScraper, normalize_url, successful_pages

__all__ = ["ScrapeError", "WebScraper", "normalize_url", "successful_pages"]

