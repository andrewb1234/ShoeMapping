from __future__ import annotations

import argparse
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set
from urllib.parse import urljoin, urlparse

import cloudscraper
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


BASE_URL = "https://runrepeat.com"
DEFAULT_OUTPUT = Path("data/runrepeat_lab_tests.sqlite")
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)

RESERVED_PATH_PREFIXES = {
    "about",
    "best",
    "catalog",
    "deals",
    "faq",
    "footwear-testing-services",
    "guides",
    "hiring",
    "legal-disclaimer",
    "news",
    "privacy",
    "sitemap",
    "terms",
}

SPECS_FIELDS = [
    "Terrain",
    "Arch Support",
    "Pronation",
    "Arch Type",
    "Use",
    "Strike Pattern",
    "Pace",
]

HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

SPEC_VALUE_TO_FIELD = {
    "road": "Terrain",
    "trail": "Terrain",
    "neutral": "Arch Support",
    "supportive": "Arch Support",
    "stability": "Arch Support",
    "neutral pronation": "Pronation",
    "supination": "Pronation",
    "underpronation": "Pronation",
    "overpronation": "Pronation",
    "high arch": "Arch Type",
    "low arch": "Arch Type",
    "flat arch": "Arch Type",
    "treadmill": "Use",
    "jogging": "Use",
    "all-day wear": "Use",
    "heel strike": "Strike Pattern",
    "forefoot/midfoot strike": "Strike Pattern",
    "competition": "Pace",
    "daily running": "Pace",
    "tempo": "Pace",
    "marathon": "Pace",
    "5k and 10k": "Pace",
    "half marathon": "Pace",
}


@dataclass
class ShoeRecord:
    shoe_id: str
    brand: str
    shoe_name: str
    source_url: str
    lab_test_results: Dict[str, str]
    crawled_at: str
    audience_verdict: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        result = {
            "shoe_id": self.shoe_id,
            "brand": self.brand,
            "shoe_name": self.shoe_name,
            "source_url": self.source_url,
            "lab_test_results": self.lab_test_results,
            "crawled_at": self.crawled_at,
        }
        if self.audience_verdict is not None:
            result["audience_verdict"] = self.audience_verdict
        return result


class RunRepeatCrawler:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: int = 20,
        delay_seconds: float = 0.15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.delay_seconds = delay_seconds

        # Use cloudscraper to bypass Cloudflare protection
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True,
            }
        )

    def _get(self, url: str) -> cloudscraper.CloudScraper:
        """Fetch URL with Cloudflare bypass and proper error logging."""
        try:
            response = self.session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            time.sleep(self.delay_seconds)
            return response
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {type(e).__name__}: {e}")
            raise

    def discover_shoe_urls(self, max_urls: Optional[int] = None) -> List[str]:
        """Discover shoe URLs by parsing catalog pages from the running-shoes sitemap."""
        # Use only the running-shoes sitemap
        running_shoes_sitemap = urljoin(self.base_url + "/", "sitemap/running-shoes")
        logger.info(f"Using running shoes sitemap: {running_shoes_sitemap}")
        
        # Extract all URLs from the running shoes sitemap
        all_urls = self._extract_urls_from_html_sitemap(running_shoes_sitemap)
        
        # Filter for catalog pages (they contain the actual shoe listings)
        catalog_urls = [url for url in all_urls if "/catalog/" in url]
        logger.info(f"Found {len(catalog_urls)} catalog pages")
        
        # Extract shoe URLs from each catalog page
        shoe_urls: Set[str] = set()
        for catalog_url in catalog_urls:
            urls = self._extract_shoe_urls_from_catalog(catalog_url)
            shoe_urls.update(urls)
        
        logger.info(f"Total shoe URLs discovered: {len(shoe_urls)}")
        
        # Filter candidates
        candidate_shoe_urls = [url for url in shoe_urls if self._is_candidate_shoe_url(url)]
        candidate_shoe_urls = sorted(set(candidate_shoe_urls))
        logger.info(f"Filtered to {len(candidate_shoe_urls)} candidate shoe URLs")
        
        if max_urls is not None:
            candidate_shoe_urls = candidate_shoe_urls[:max_urls]
        return candidate_shoe_urls

    
    def _extract_urls_from_html_sitemap(self, sitemap_url: str) -> Set[str]:
        """Extract all shoe URLs from an HTML sitemap page."""
        urls: Set[str] = set()
        
        try:
            response = self._get(sitemap_url)
        except Exception as e:
            logger.warning(f"Failed to fetch sitemap {sitemap_url}: {e}")
            return urls
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find all links on the sitemap page
        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            
            # Convert relative URLs to absolute
            if href.startswith("/"):
                href = urljoin(self.base_url + "/", href)
            
            # Only include URLs from the same domain
            if href.startswith(self.base_url):
                urls.add(href)
        
        
        logger.info(f"Sitemap {sitemap_url} contains {len(urls)} URLs")
        return urls

    def _extract_shoe_urls_from_catalog(self, catalog_url: str) -> Set[str]:
        """Extract individual shoe URLs from a catalog page."""
        urls: Set[str] = set()
        
        try:
            response = self._get(catalog_url)
        except Exception as e:
            logger.warning(f"Failed to fetch catalog {catalog_url}: {e}")
            return urls
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find links that look like individual shoe pages
        for link in soup.find_all("a", href=True):
            href = link["href"].strip()
            
            # Convert relative URLs to absolute
            if href.startswith("/"):
                href = urljoin(self.base_url + "/", href)
            
            # Look for single-slug URLs (individual shoe pages)
            if href.startswith(self.base_url):
                parsed = urlparse(href)
                path = parsed.path.strip("/")
                
                # Individual shoe pages have a single slug (no slashes in path)
                if path and "/" not in path and path not in RESERVED_PATH_PREFIXES:
                    urls.add(href)
        
        logger.info(f"Catalog {catalog_url} contains {len(urls)} shoe URLs")
        return urls

    def _is_candidate_shoe_url(self, url: str) -> bool:
        if not url.startswith(self.base_url):
            return False

        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if not path or "/" in path:
            return False

        slug = path.lower()
        
        # Filter out known non-shoe paths
        if slug in RESERVED_PATH_PREFIXES:
            logger.debug(f"Filtered out reserved path: {slug}")
            return False
        if any(slug.startswith(prefix + "-") for prefix in RESERVED_PATH_PREFIXES):
            logger.debug(f"Filtered out path with reserved prefix: {slug}")
            return False

        # For now, just filter out the obvious non-shoe pages
        # We'll rely on the page content validation to filter further

        is_valid = bool(re.fullmatch(r"[a-z0-9-]+", slug))
        if not is_valid:
            logger.debug(f"Filtered out invalid slug format: {slug}")
        return is_valid

    def crawl_shoe_page(self, shoe_url: str) -> Optional[ShoeRecord]:
        try:
            response = self._get(shoe_url)
        except Exception as e:
            logger.warning(f"Failed to crawl {shoe_url}: {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        shoe_name = self._extract_shoe_name(soup)
        if not shoe_name:
            return None

        brand = self._extract_brand(soup, shoe_name)
        if not brand:
            return None

        lab_results = self._extract_lab_test_results(soup, shoe_name)
        if not lab_results:
            return None

        specs = self._extract_specs(soup)
        if specs:
            lab_results.update(specs)

        if self._is_non_running_shoe(lab_results):
            logger.info(f"Skipping non-running shoe without Terrain/Pace: {shoe_name} ({shoe_url})")
            return None

        audience_verdict = self._extract_audience_verdict(soup)

        shoe_id = self._build_shoe_id(brand, shoe_name)
        return ShoeRecord(
            shoe_id=shoe_id,
            brand=brand,
            shoe_name=shoe_name,
            source_url=shoe_url,
            lab_test_results=lab_results,
            audience_verdict=audience_verdict,
            crawled_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    def _extract_shoe_name(self, soup: BeautifulSoup) -> Optional[str]:
        h1 = soup.find("h1")
        if not h1:
            return None
        name = " ".join(h1.get_text(" ", strip=True).split())
        # Remove " Review" suffix if present
        if name and name.lower().endswith(" review"):
            name = name[:-7].strip()  # Remove " review" (7 chars)
        return name or None

    def _extract_brand(self, soup: BeautifulSoup, shoe_name: str) -> Optional[str]:
        breadcrumb_candidates = soup.select('a[href^="/catalog/"]')
        for tag in breadcrumb_candidates:
            text = " ".join(tag.get_text(" ", strip=True).split())
            if text and text.lower() in shoe_name.lower():
                return text

        return shoe_name.split()[0] if shoe_name else None

    def _extract_lab_test_results(self, soup: BeautifulSoup, shoe_name: str) -> Dict[str, str]:
        heading = soup.find(string=re.compile(r"Lab\s*Test\s*Results", re.IGNORECASE))
        if not heading:
            return {}

        table = heading.find_parent().find_next("table") if heading.find_parent() else None
        if not table:
            table = soup.find("table")
        if not table:
            return {}

        rows = table.find_all("tr")
        if not rows:
            return {}

        header_cells = rows[0].find_all(["th", "td"])
        headers = [self._clean_text(cell.get_text(" ", strip=True)) for cell in header_cells]
        shoe_col_idx = self._resolve_shoe_column_index(headers, shoe_name)
        if shoe_col_idx is None:
            return {}

        results: Dict[str, str] = {}
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= shoe_col_idx:
                continue

            metric_name = self._clean_text(cells[0].get_text(" ", strip=True))
            metric_value = self._clean_text(cells[shoe_col_idx].get_text(" ", strip=True))

            if metric_name and metric_value:
                results[metric_name] = metric_value

        return results

    def _extract_specs(self, soup: BeautifulSoup) -> Dict[str, str]:
        heading = self._find_specs_heading(soup)
        if heading is None:
            return {}

        section_nodes = self._collect_specs_section_nodes(heading)
        if not section_nodes:
            return {}

        specs: Dict[str, List[str]] = {field: [] for field in SPECS_FIELDS}

        for node in section_nodes:
            if not hasattr(node, "get_text"):
                continue

            for raw_line in node.get_text("\n", strip=True).splitlines():
                self._capture_specs_value(specs, raw_line)

            for link in node.find_all("a", href=True):
                link_text = self._clean_text(link.get_text(" ", strip=True))
                link_href = link.get("href", "")
                field_name = self._classify_specs_value(link_text) or self._classify_specs_href(link_href)
                if field_name:
                    self._append_spec_value(specs, field_name, link_text)

        filtered = {
            field_name: " | ".join(values)
            for field_name, values in specs.items()
            if values
        }

        if filtered:
            logger.debug(f"Extracted Specs fields: {list(filtered.keys())}")
        return filtered

    def _find_specs_heading(self, soup: BeautifulSoup):
        for heading_text in ("Specs (brand)", "Specs"):
            heading = soup.find(
                lambda tag: getattr(tag, "name", None) in HEADING_TAGS
                and self._normalize_text(tag.get_text(" ", strip=True)) == self._normalize_text(heading_text)
            )
            if heading is not None:
                return heading

        heading_string = soup.find(string=re.compile(r"Specs\s*\(brand\)|Specs", re.IGNORECASE))
        if heading_string is None:
            return None

        for ancestor in heading_string.parents:
            if getattr(ancestor, "name", None) in HEADING_TAGS:
                return ancestor

        return None

    def _collect_specs_section_nodes(self, heading) -> List[object]:
        nodes: List[object] = []

        for sibling in heading.next_siblings:
            if getattr(sibling, "name", None) in HEADING_TAGS:
                break
            if getattr(sibling, "name", None) or self._clean_text(str(sibling)):
                nodes.append(sibling)

        return nodes

    def _capture_specs_value(self, specs: Dict[str, List[str]], raw_value: str) -> None:
        for chunk in raw_value.split("|"):
            value = self._clean_text(chunk)
            if not value:
                continue

            field_name = self._classify_specs_value(value)
            if field_name:
                self._append_spec_value(specs, field_name, value)

    def _classify_specs_value(self, value: str) -> Optional[str]:
        normalized = self._normalize_text(value).rstrip(":")
        if normalized in SPEC_VALUE_TO_FIELD:
            return SPEC_VALUE_TO_FIELD[normalized]

        if ":" in normalized:
            normalized = self._normalize_text(normalized.split(":", 1)[1])
            if normalized in SPEC_VALUE_TO_FIELD:
                return SPEC_VALUE_TO_FIELD[normalized]

        return None

    def _classify_specs_href(self, href: str) -> Optional[str]:
        parsed = urlparse(href)
        slug = parsed.path.rstrip("/").split("/")[-1].lower()

        if slug in {"road-running-shoes", "trail-running-shoes"}:
            return "Terrain"
        if slug in {"neutral-running-shoes", "supportive-running-shoes", "stability-running-shoes"}:
            return "Arch Support"
        if slug in {"supination-running-shoes", "underpronation-running-shoes", "neutral-pronation-running-shoes", "overpronation-running-shoes"}:
            return "Pronation"
        if slug in {"high-arch-running-shoes", "low-arch-running-shoes", "flat-arch-running-shoes"}:
            return "Arch Type"
        if slug in {"treadmill-running-shoes", "jogging-running-shoes", "all-day-wear-running-shoes"}:
            return "Use"
        if slug in {"heel-strike-running-shoes", "forefoot-midfoot-strike-running-shoes"}:
            return "Strike Pattern"
        if slug in {"daily-running-running-shoes", "tempo-running-shoes", "competition-running-shoes", "marathon-running-shoes", "5k-and-10k-running-shoes", "half-marathon-running-shoes"}:
            return "Pace"

        return None

    @staticmethod
    def _append_spec_value(specs: Dict[str, List[str]], field_name: str, value: str) -> None:
        bucket = specs.setdefault(field_name, [])
        if value not in bucket:
            bucket.append(value)

    @staticmethod
    def _is_non_running_shoe(lab_results: Dict[str, str]) -> bool:
        return not lab_results.get("Terrain") and not lab_results.get("Pace")

    def _extract_audience_verdict(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract the Audience Verdict score from the shoe page."""
        # Look for the audience verdict section
        audience_heading = soup.find(string=re.compile(r"Audience\s+verdict", re.IGNORECASE))
        if not audience_heading:
            return None

        # Find the score element (usually a div with the score number)
        # First try to find it near the heading
        heading_parent = audience_heading.find_parent()
        if heading_parent:
            # Look for a div containing the score (typically a large number)
            score_elements = heading_parent.find_all("div")
            for elem in score_elements:
                text = elem.get_text(strip=True)
                # Check if it's a number (the score)
                if text.isdigit() and len(text) <= 3:  # Scores are typically 1-100
                    try:
                        score = int(text)
                        if 0 <= score <= 100:  # Validate score range
                            return score
                    except ValueError:
                        continue

        # Fallback: look for any element with class containing 'verdict' or 'score'
        verdict_elements = soup.find_all(class_=re.compile(r"verdict|score", re.IGNORECASE))
        for elem in verdict_elements:
            text = elem.get_text(strip=True)
            if text.isdigit() and len(text) <= 3:
                try:
                    score = int(text)
                    if 0 <= score <= 100:
                        return score
                except ValueError:
                    continue

        return None

    def _resolve_shoe_column_index(self, headers: List[str], shoe_name: str) -> Optional[int]:
        if not headers:
            return None

        normalized_headers = [h.lower() for h in headers]

        for idx, header in enumerate(normalized_headers):
            if shoe_name.lower() in header and header:
                return idx

        average_idx = None
        for idx, header in enumerate(normalized_headers):
            if header.startswith("average"):
                average_idx = idx
                break

        if average_idx is not None:
            for idx in range(average_idx - 1, -1, -1):
                if headers[idx]:
                    return idx

        if len(headers) > 1:
            return 1

        return None

    @staticmethod
    def _clean_text(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()

    @staticmethod
    def _build_shoe_id(brand: str, shoe_name: str) -> str:
        return f"{brand.strip()}::{shoe_name.strip()}"




def crawl(
    max_shoes: Optional[int],
    workers: int,
    output_path: Path,
    delay_seconds: float,
    rebuild_db: bool,
) -> None:
    from database import init_database, get_existing_shoe_ids, save_shoe_records
    
    if rebuild_db and output_path.exists():
        logger.warning(f"Rebuilding database, removing existing file: {output_path}")
        output_path.unlink()

    # Initialize database
    init_database(output_path)
    
    crawler = RunRepeatCrawler(delay_seconds=delay_seconds)
    existing_shoe_ids = get_existing_shoe_ids(output_path)

    shoe_urls = crawler.discover_shoe_urls(max_urls=max_shoes)
    print(f"Discovered {len(shoe_urls)} candidate shoe URLs")
    
    # Filter out already crawled shoes
    new_urls = []
    for url in shoe_urls:
        # Extract shoe_id from URL (last part of path)
        shoe_slug = url.split('/')[-1]
        # Check if this shoe was already crawled
        is_duplicate = False
        for existing_id in existing_shoe_ids:
            # Extract shoe name from existing shoe_id (after ::)
            existing_shoe_name = existing_id.split("::")[-1]
            # Normalize both by converting to lowercase and handling hyphens
            shoe_slug_norm = shoe_slug.lower().replace("-", " ")
            existing_name_norm = existing_shoe_name.lower()
            # Compare normalized names
            if shoe_slug_norm == existing_name_norm:
                is_duplicate = True
                break
        if not is_duplicate:
            new_urls.append(url)
    print(f"Skipping {len(shoe_urls) - len(new_urls)} already crawled shoes")
    print(f"Crawling {len(new_urls)} new shoes")

    new_records: Dict[str, ShoeRecord] = {}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(crawler.crawl_shoe_page, url): url for url in new_urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                record = future.result()
            except Exception:
                continue

            if not record:
                continue

            new_records[record.shoe_id] = record
            print(f"Captured: {record.shoe_id} ({len(record.lab_test_results)} metrics) from {url}")

    # Save to database
    save_shoe_records(output_path, new_records)

    print(f"Saved {len(new_records)} new shoe records to {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl RunRepeat shoe pages and extract Lab Test Results shoe-column values."
    )
    parser.add_argument(
        "--max-shoes",
        type=int,
        default=None,
        help="Limit number of candidate shoe URLs to crawl (useful for testing).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent page workers.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.15,
        help="Delay after each request per worker.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output SQLite datastore path.",
    )
    parser.add_argument(
        "--rebuild-db",
        action="store_true",
        help="Delete the existing SQLite datastore before crawling.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    crawl(
        max_shoes=args.max_shoes,
        workers=max(1, args.workers),
        output_path=args.output,
        delay_seconds=max(0.0, args.delay_seconds),
        rebuild_db=args.rebuild_db,
    )


if __name__ == "__main__":
    main()
