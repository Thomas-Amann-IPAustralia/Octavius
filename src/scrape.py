#!/usr/bin/env python3
"""Phase 1: Scrape the Australian Government Style Manual website to markdown."""

import hashlib
import json
import logging
import os
import random
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager
import trafilatura

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

REPO_ROOT = Path(__file__).parent.parent
CONTENT_DIR = REPO_ROOT / "content"
SITEMAP_STATE_FILE = REPO_ROOT / "sitemap_state.json"
CONTENT_MANIFEST_FILE = REPO_ROOT / "content_manifest.json"

PAGE_LOAD_TIMEOUT = 25

FAILURE_SIGNATURES = [
    "This site can't be reached",
    "ERR_HTTP2_PROTOCOL_ERROR",
    "Enable JavaScript and cookies to continue",
    "Checking if the site connection is secure",
    "Just a moment...",
    "Verifying you are human",
    "DDoS protection by Cloudflare",
    "Access denied",
]

BOT_USER_AGENT = (
    "OctaviusRulebookBot/1.0 (+https://github.com/thomas-amann-ipaustralia/octavius)"
)


def initialize_driver(with_proxy: bool = False) -> Optional[webdriver.Chrome]:
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--lang=en-US,en;q=0.9")
    # NOTE: Keep this generic User-Agent for stealth; the descriptive bot UA is sent
    # via a separate HTTP header in the sitemap/robots.txt fetch only (use requests lib).
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    if with_proxy:
        proxy_host, proxy_port, proxy_user, proxy_pass = (
            os.environ.get(k) for k in ["PROXY_HOST", "PROXY_PORT", "PROXY_USER", "PROXY_PASS"]
        )
        if all([proxy_host, proxy_port, proxy_user, proxy_pass]):
            chrome_options.add_argument(
                f"--proxy-server=http://{proxy_user}:{proxy_pass}@{proxy_host}:{proxy_port}"
            )
        else:
            log.warning("Proxy requested but credentials incomplete — skipping proxy init")
            return None

    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        stealth(
            driver,
            languages=["en-US", "en"],
            vendor="Google Inc.",
            platform="Win32",
            webgl_vendor="Intel Inc.",
            renderer="Intel Iris OpenGL Engine",
            fix_hairline=True,
        )
        return driver
    except Exception as e:
        log.error("Failed to initialize WebDriver: %s", e)
        return None


def check_robots_txt(base_url: str) -> bool:
    """Check robots.txt. Returns True if scraping is allowed, False if disallowed."""
    robots_url = f"{base_url}/robots.txt"
    try:
        resp = requests.get(
            robots_url,
            headers={"User-Agent": BOT_USER_AGENT},
            timeout=15,
        )
        log.info("robots.txt response (status %s):\n%s", resp.status_code, resp.text[:2000])

        if resp.status_code == 404:
            log.info("No robots.txt found — proceeding.")
            return True

        lines = resp.text.splitlines()
        current_agent_applies = False
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("user-agent:"):
                agent = line.split(":", 1)[1].strip()
                current_agent_applies = agent == "*" or "octavius" in agent.lower()
            elif current_agent_applies:
                if line.lower().startswith("disallow:"):
                    path = line.split(":", 1)[1].strip()
                    if path == "/":
                        log.error("robots.txt disallows all crawling. Aborting.")
                        return False
                elif line.lower().startswith("crawl-delay:"):
                    delay = line.split(":", 1)[1].strip()
                    log.warning("robots.txt specifies Crawl-delay: %s. Will respect this.", delay)
        return True
    except Exception as e:
        log.warning("Could not fetch robots.txt: %s — proceeding anyway.", e)
        return True


def strip_noise(html: str) -> str:
    """Remove navigation noise from HTML before passing to trafilatura."""
    soup = BeautifulSoup(html, "lxml")
    for selector in ["nav", "footer", "header", "script", "style", "aside"]:
        for tag in soup.find_all(selector):
            tag.decompose()
    for tag in soup.find_all(class_="noprint"):
        tag.decompose()
    sidebar = soup.find(id="sidebar")
    if sidebar:
        sidebar.decompose()
    return str(soup)


def check_block_page(html: str) -> bool:
    """Returns True if the page appears to be a block/error page."""
    html_lower = html.lower()
    for sig in FAILURE_SIGNATURES:
        if sig.lower() in html_lower:
            log.warning("Block-page signature detected: %s", sig)
            return True
    return False


def fetch_with_retry(url: str, driver: webdriver.Chrome) -> Optional[str]:
    """Fetch a URL with Selenium, with proxy fallback and exponential backoff on 429/503."""
    for attempt in range(3):
        try:
            driver.get(url)
            WebDriverWait(driver, PAGE_LOAD_TIMEOUT).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            # Scroll simulation
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 4);")
            time.sleep(random.uniform(2, 4))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
            time.sleep(random.uniform(1, 3))

            html = driver.page_source
            if check_block_page(html):
                log.warning("Block page detected on attempt %d for %s", attempt + 1, url)
                proxy_driver = initialize_driver(with_proxy=True)
                if proxy_driver:
                    log.info("Retrying with proxy for %s", url)
                    try:
                        proxy_driver.get(url)
                        WebDriverWait(proxy_driver, PAGE_LOAD_TIMEOUT).until(
                            EC.presence_of_element_located((By.TAG_NAME, "body"))
                        )
                        html = proxy_driver.page_source
                    finally:
                        proxy_driver.quit()
                    if not check_block_page(html):
                        return html
                return None
            return html
        except WebDriverException as e:
            wait = 30 * (2 ** attempt)
            log.warning(
                "Fetch failed for %s (attempt %d): %s. Waiting %ds.",
                url, attempt + 1, e, wait,
            )
            time.sleep(wait)

    log.error("All retries exhausted for %s", url)
    return None


SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def fetch_sitemap_with_retry(url: str) -> Optional[bytes]:
    """Fetch a sitemap XML document via ``requests`` with exponential backoff.

    The pipeline design (see CLAUDE_Octavius Rulebook Creation Pipeline.md)
    prescribes using ``requests`` for robots.txt and sitemap fetches so that
    the descriptive OctaviusRulebookBot User-Agent is sent — and so Chrome's
    in-browser XML viewer does not interfere with the raw bytes. Full-page
    fetches continue to use Selenium.
    """
    for attempt in range(3):
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": BOT_USER_AGENT,
                    "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
                },
                timeout=30,
            )
            if resp.status_code in (429, 503):
                wait = 30 * (2 ** attempt)
                log.warning(
                    "Sitemap fetch rate-limited (HTTP %s) on attempt %d. Waiting %ds.",
                    resp.status_code, attempt + 1, wait,
                )
                time.sleep(wait)
                continue
            resp.raise_for_status()
            if not resp.content:
                log.warning(
                    "Sitemap fetch returned empty body on attempt %d", attempt + 1
                )
                continue
            return resp.content
        except requests.RequestException as e:
            wait = 30 * (2 ** attempt)
            log.warning(
                "Sitemap fetch failed (attempt %d): %s. Waiting %ds.",
                attempt + 1, e, wait,
            )
            time.sleep(wait)

    log.error("All retries exhausted for sitemap %s", url)
    return None


def _local(tag: str) -> str:
    """Return the local name of an XML tag (strip any ``{ns}`` prefix)."""
    return tag.split("}", 1)[1] if "}" in tag else tag


def parse_sitemap(
    xml_bytes: bytes,
    source_url: str,
    seen: Optional[set] = None,
) -> list[dict]:
    """Parse a sitemap XML document and return a list of ``{loc, lastmod}`` dicts.

    Handles both ``<urlset>`` and ``<sitemapindex>`` roots. For sitemap
    indexes the nested sitemaps are fetched via ``fetch_sitemap_with_retry``
    and parsed recursively. The ``seen`` set guards against cycles.
    """
    if seen is None:
        seen = set()
    seen.add(source_url)

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        log.error("Failed to parse sitemap XML from %s: %s", source_url, e)
        log.error("First 500 bytes of response: %r", xml_bytes[:500])
        return []

    ns = {"sm": SITEMAP_NS}
    root_local = _local(root.tag).lower()

    urls: list[dict] = []

    if root_local == "sitemapindex":
        # Nested sitemaps — recurse into each.
        nested_locs: list[str] = []
        for sm in root.findall("sm:sitemap", ns) or root.findall("sitemap"):
            loc = sm.findtext("sm:loc", namespaces=ns)
            if loc is None:
                loc_el = sm.find("loc")
                loc = loc_el.text if loc_el is not None else None
            if loc:
                nested_locs.append(loc.strip())

        log.info(
            "Sitemap at %s is an index with %d nested sitemap(s)",
            source_url, len(nested_locs),
        )

        for loc in nested_locs:
            if loc in seen:
                log.debug("Skipping already-seen nested sitemap %s", loc)
                continue
            log.info("Fetching nested sitemap: %s", loc)
            nested_bytes = fetch_sitemap_with_retry(loc)
            if nested_bytes is None:
                log.warning("Failed to fetch nested sitemap %s — skipping", loc)
                continue
            urls.extend(parse_sitemap(nested_bytes, loc, seen))
            # Small politeness delay between nested sitemap fetches.
            time.sleep(random.uniform(1, 2))
        return urls

    if root_local == "urlset":
        url_elems = root.findall("sm:url", ns) or root.findall("url")
        for url_elem in url_elems:
            loc = url_elem.findtext("sm:loc", namespaces=ns)
            if loc is None:
                loc_el = url_elem.find("loc")
                loc = loc_el.text if loc_el is not None else None
            lastmod = url_elem.findtext("sm:lastmod", namespaces=ns)
            if lastmod is None:
                lm_el = url_elem.find("lastmod")
                lastmod = lm_el.text if lm_el is not None else None
            if loc:
                urls.append({"loc": loc.strip(), "lastmod": lastmod})
        return urls

    log.error(
        "Unexpected sitemap root element <%s> at %s — expected <urlset> or <sitemapindex>",
        root.tag, source_url,
    )
    log.error("First 500 bytes of response: %r", xml_bytes[:500])
    return []


def url_to_filepath(url: str) -> Path:
    """Convert a URL to a relative content/ filepath."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        path = "index"
    return CONTENT_DIR / f"{path}.md"


def html_to_markdown(html: str) -> Optional[str]:
    """Convert cleaned HTML to markdown via trafilatura."""
    return trafilatura.extract(
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(message: str, files: list[str]) -> None:
    """Stage and commit specific files."""
    subprocess.run(
        ["git", "config", "user.name", "OctaviusBot"], check=True, cwd=REPO_ROOT
    )
    subprocess.run(
        ["git", "config", "user.email", "octavius-bot@users.noreply.github.com"],
        check=True,
        cwd=REPO_ROOT,
    )
    subprocess.run(["git", "add", "--"] + files, check=True, cwd=REPO_ROOT)
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=REPO_ROOT)
    if result.returncode == 0:
        log.info("Nothing to commit.")
        return
    subprocess.run(["git", "commit", "-m", message], check=True, cwd=REPO_ROOT)


def main() -> None:
    sitemap_url = os.environ.get("SITEMAP_URL")
    if not sitemap_url:
        raise SystemExit("SITEMAP_URL environment variable not set")

    parsed_sitemap = urlparse(sitemap_url)
    base_url = f"{parsed_sitemap.scheme}://{parsed_sitemap.netloc}"

    # Step 2: Check robots.txt — mandatory on every run
    if not check_robots_txt(base_url):
        raise SystemExit("robots.txt check failed. Aborting scrape.")

    # Fetch the sitemap via `requests` first (per the pipeline design) so the
    # descriptive bot User-Agent is used and Chrome's in-browser XML viewer
    # cannot interfere with the raw bytes. Resolve sitemap indexes recursively.
    log.info("Fetching sitemap from %s", sitemap_url)
    sitemap_bytes = fetch_sitemap_with_retry(sitemap_url)
    if sitemap_bytes is None:
        raise SystemExit("Failed to fetch sitemap after retries. Aborting.")

    urls = parse_sitemap(sitemap_bytes, sitemap_url)
    log.info("Found %d URLs in sitemap", len(urls))

    if not urls:
        raise SystemExit(
            "Sitemap parsed but yielded 0 URLs. Check the sitemap root element "
            "and namespace — see the error logs above for a content snippet."
        )

    # Initialise Selenium driver for per-page fetches (JS rendering + stealth).
    driver = initialize_driver()
    if not driver:
        raise RuntimeError("Failed to initialize WebDriver")

    try:
        # Load sitemap state
        if SITEMAP_STATE_FILE.exists():
            with open(SITEMAP_STATE_FILE) as f:
                sitemap_state = json.load(f)
        else:
            sitemap_state = {}

        # Determine which URLs are new or changed
        urls_to_scrape = [
            entry for entry in urls
            if entry["loc"] not in sitemap_state
            or sitemap_state[entry["loc"]] != entry.get("lastmod")
        ]

        log.info("%d URLs need scraping (new or changed)", len(urls_to_scrape))

        if not urls_to_scrape:
            log.info("No new/changed pages. Exiting.")
            return

        CONTENT_DIR.mkdir(parents=True, exist_ok=True)

        failed_urls: list[str] = []
        scraped_files: list[str] = []

        for i, entry in enumerate(urls_to_scrape):
            url = entry["loc"]
            log.info("[%d/%d] Scraping %s", i + 1, len(urls_to_scrape), url)

            html = fetch_with_retry(url, driver)
            if html is None:
                log.error("Failed to fetch %s — skipping", url)
                failed_urls.append(url)
                continue

            # Strip navigation noise before passing to trafilatura
            clean_html = strip_noise(html)

            # Convert to markdown
            markdown = html_to_markdown(clean_html)
            if not markdown:
                log.warning("trafilatura returned no content for %s — skipping", url)
                failed_urls.append(url)
                continue

            # Write to file using URL path segments as directory structure
            filepath = url_to_filepath(url)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(markdown, encoding="utf-8")

            # Update state for this URL
            sitemap_state[url] = entry.get("lastmod")
            scraped_files.append(str(filepath.relative_to(REPO_ROOT)))
            log.info("Wrote %s", filepath.relative_to(REPO_ROOT))

            # Politeness delay between requests
            if i < len(urls_to_scrape) - 1:
                delay = random.uniform(2, 4)
                log.debug("Politeness sleep %.1fs", delay)
                time.sleep(delay)
    finally:
        driver.quit()

    if failed_urls:
        log.warning("Failed URLs (%d): %s", len(failed_urls), failed_urls)

    # Write sitemap state
    with open(SITEMAP_STATE_FILE, "w") as f:
        json.dump(sitemap_state, f, indent=2)

    # Write content manifest (SHA-256 of every .md file in content/)
    manifest_files: dict[str, str] = {}
    for md_file in sorted(CONTENT_DIR.rglob("*.md")):
        rel_path = str(md_file.relative_to(REPO_ROOT))
        manifest_files[rel_path] = sha256_file(md_file)

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": manifest_files,
    }
    with open(CONTENT_MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    log.info("Wrote content manifest with %d files", len(manifest_files))

    # Git-commit content, sitemap state, and manifest together
    commit_files = (
        [str(SITEMAP_STATE_FILE.relative_to(REPO_ROOT))]
        + [str(CONTENT_MANIFEST_FILE.relative_to(REPO_ROOT))]
        + scraped_files
    )
    git_commit(
        f"Phase 1: scrape {len(scraped_files)} pages from Style Manual",
        commit_files,
    )

    log.info(
        "Phase 1 complete. %d pages scraped, %d failed.",
        len(scraped_files),
        len(failed_urls),
    )


if __name__ == "__main__":
    main()
