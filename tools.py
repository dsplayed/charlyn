"""Tool implementations for Charlyn."""
import os

# Playwright's sync API raises if an asyncio loop is detected running.
# This env var disables that check so we can use sync Playwright from threads.
os.environ.setdefault("PLAYWRIGHT_SKIP_ASYNCIO_CHECK", "1")

import io
import re
import glob
import textwrap
from datetime import datetime
from typing import List, Optional

import hashlib
import uuid
import socket
import ssl
import qrcode
from urllib.parse import urlparse, parse_qs
from urllib.parse import quote as url_quote

import requests
from PIL import Image, ImageEnhance
import pytesseract
from playwright.sync_api import sync_playwright, Page, BrowserContext

from config import (
    SCREENSHOTS_DIR, BROWSER_TIMEOUT, HEADLESS, YOLO,
    SERPER_API_KEY, SEARCH_REGION, CACHE_TTL, SANDBOX_ENABLED,
)
import vnc_ctl
from cache import cached, clear as cache_clear
from timers import timer_manager
from sandbox import get_current as get_sandbox, SandboxError, is_docker_available
from sites import publish as sites_publish, list_publications as sites_list
from video import (
    anime_download as video_anime_download,
    download_and_upload as video_download_and_upload,
    upload_to_storage_to as video_upload_to_storage_to,
    register_with_worker as video_register_with_worker,
)

# ──────────────────────────────────────────────
# Browser
# ──────────────────────────────────────────────

class BrowserTool:
    """Playwright-based browser automation."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._screenshot_counter = 0

    def _ensure_page(self) -> Page:
        if self._page is None:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=HEADLESS)
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            self._page = self._context.new_page()
            self._page.set_default_timeout(BROWSER_TIMEOUT)
        return self._page

    def _handle_error(self, e: Exception) -> str:
        err = str(e).lower()
        if "closed" in err or "crashed" in err:
            self._reset_browser()
            return f"Browser context was closed/crashed. It has been reset. Please retry the action."
        return str(e)

    def _reset_browser(self):
        try:
            if self._browser:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def navigate(self, url: str) -> str:
        page = self._ensure_page()
        if not url.startswith("http"):
            url = "https://" + url
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            title = page.title()
            text = self._extract_visible_text(page)
            return f"Title: {title}\nURL: {page.url}\n--- Content (first 3000 chars) ---\n{text[:3000]}"
        except Exception as e:
            return f"Error navigating to {url}: {self._handle_error(e)}"

    def click(self, selector: str) -> str:
        page = self._ensure_page()
        try:
            if page.locator(selector).count() > 0:
                page.locator(selector).first.click()
            else:
                page.get_by_text(selector, exact=False).first.click()
            page.wait_for_timeout(1000)
            return f"Clicked '{selector}'. New title: {page.title()}. URL: {page.url}"
        except Exception as e:
            return f"Error clicking '{selector}': {self._handle_error(e)}"

    def type_text(self, selector: str, text: str) -> str:
        page = self._ensure_page()
        try:
            if page.locator(selector).count() > 0:
                loc = page.locator(selector).first
            else:
                loc = page.get_by_role("textbox").filter(has_text=selector).first
            loc.fill(text)
            return f"Typed '{text}' into '{selector}'."
        except Exception as e:
            return f"Error typing into '{selector}': {self._handle_error(e)}"

    def screenshot(self) -> str:
        page = self._ensure_page()
        self._screenshot_counter += 1
        filename = f"screenshot_{self._screenshot_counter:03d}.png"
        path = os.path.join(SCREENSHOTS_DIR, filename)
        page.screenshot(path=path, full_page=True)
        return path

    def _extract_visible_text(self, page: Page) -> str:
        try:
            return page.inner_text("body")
        except Exception:
            return ""

    def close(self):
        self._reset_browser()


# ──────────────────────────────────────────────
# OCR
# ──────────────────────────────────────────────

def ocr_analyze(image_path: str) -> str:
    if not os.path.exists(image_path):
        return f"Error: Image not found at {image_path}"
    try:
        img = Image.open(image_path)
        if img.mode != "L":
            img = img.convert("L")
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)
        text = pytesseract.image_to_string(img)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        words = [w for w in data["text"] if w.strip()]
        return (
            f"--- OCR Text ---\n{text.strip()}\n"
            f"--- Word count: {len(words)} ---\n"
            f"If text is garbled, the image may be low-resolution or stylized."
        )
    except Exception as e:
        return f"OCR Error: {e}"


# ──────────────────────────────────────────────
# Web Search (cached)
# ──────────────────────────────────────────────

@cached(CACHE_TTL)
def web_search(query: str, gl: str = "th", timeout: int = 8) -> str:
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            json={"q": query, "gl": gl},
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic", [])
        if not organic:
            return "No search results found. Try a different query or use browser_navigate to a specific site."
        out = []
        for i, r in enumerate(organic[:8], 1):
            title = r.get("title", "No title")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            out.append(f"{i}. {title}\n   URL: {link}\n   {snippet.strip()}")
        return "Search Results:\n" + "\n\n".join(out)
    except Exception as e:
        return f"Search error: {e}. Try using browser_navigate to a specific site instead."


@cached(CACHE_TTL)
def web_scrape(url: str, timeout: int = 15) -> str:
    try:
        resp = requests.post(
            "https://scrape.serper.dev",
            json={"url": url},
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict) and data.get("status") == "error":
            return f"Scrape failed: {data.get('message', 'unknown error')}"
        title = data.get("metadata", {}).get("title", data.get("title", ""))
        text = data.get("text", "")
        description = data.get("description", "")
        out = f"Title: {title}\n"
        if description:
            out += f"Description: {description}\n"
        out += f"--- Content ---\n{text[:5000]}" if text else "No text content returned."
        return out
    except Exception as e:
        return f"Scrape error: {e}. Try using browser_navigate to view the page instead."


def username_search(username: str, timeout: int = 15) -> str:
    platforms = [
        ("General web (exact match)", f"\"{username}\""),
        ("GitHub", f"site:github.com inurl:{username} -inurl:awesome -inurl:topic"),
        ("Twitter / X", f"site:twitter.com {username} OR site:x.com {username}"),
        ("Reddit", f"site:reddit.com {username} -wiki -r/subreddit"),
        ("Instagram", f"site:instagram.com {username}"),
        ("LinkedIn", f"site:linkedin.com/in {username}"),
        ("YouTube", f"site:youtube.com @{username} OR site:youtube.com {username} channel"),
        ("TikTok", f"site:tiktok.com @{username}"),
        ("Twitch", f"site:twitch.tv {username}"),
        ("SoundCloud", f"site:soundcloud.com {username}"),
        ("Online Sequencer", f"site:onlinesequencer.net {username}"),
        ("Dev.to", f"site:dev.to {username}"),
        ("Medium", f"site:medium.com @{username}"),
        ("Stack Overflow", f"site:stackoverflow.com/users {username}"),
        ("Pinterest", f"site:pinterest.com {username}"),
        ("Discord / Telegram", f"site:discord.com {username} OR site:telegram.org {username} OR site:t.me {username}"),
        ("Linktree / bio", f"site:linktr.ee {username} OR site:bio.link {username} OR site:carrd.co {username}"),
        ("About.me / profiles", f"site:about.me {username} OR site:gravatar.com {username}"),
        ("Fiverr / freelancer", f"site:fiverr.com {username} OR site:upwork.com {username}"),
        ("Strava / fitness", f"site:strava.com {username}"),
        ("Spotify / music", f"site:open.spotify.com {username}"),
        ("Personal pages", f"inurl:\"{username}\" (\"about me\" OR \"profile\" OR \"contact\" OR \"@\") -sourceforge -pypi -npm -github.com/{username}"),
    ]
    out = [f"=== Username Search: {username} ===\n"]
    for label, query in platforms:
        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={"q": query, "gl": "th", "num": 5},
                headers={
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json",
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("organic", [])
            if organic:
                out.append(f"--- {label} ---")
                for r in organic[:3]:
                    title = r.get("title", "")
                    link = r.get("link", "")
                    snippet = r.get("snippet", "")
                    out.append(f"  {title}")
                    out.append(f"  {link}")
                    if snippet:
                        out.append(f"  {snippet.strip()}")
                    out.append("")
        except Exception:
            pass
    if len(out) <= 1:
        return f"No results found for username '{username}'."
    return "\n".join(out)


def web_deep_search(query: str, gl: str = "th", max_scrape: int = 3, timeout: int = 15) -> str:
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            json={"q": query, "gl": gl, "num": max_scrape + 3},
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic", [])
        if not organic:
            return "No search results found."

        out = [f"=== Deep Search: {query} ===\n"]
        for i, r in enumerate(organic[:max_scrape], 1):
            title = r.get("title", "No title")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            out.append(f"[{i}] {title}")
            out.append(f"    URL: {link}")
            out.append(f"    Snippet: {snippet.strip()}")
            try:
                scrape_resp = requests.post(
                    "https://scrape.serper.dev",
                    json={"url": link},
                    headers={
                        "X-API-KEY": SERPER_API_KEY,
                        "Content-Type": "application/json",
                    },
                    timeout=timeout,
                )
                scrape_resp.raise_for_status()
                scrape_data = scrape_resp.json()
                text = scrape_data.get("text", "")
                if text:
                    out.append(f"    --- Full Content ---\n{text[:2000].strip()}")
                else:
                    out.append("    (no text content)")
            except Exception as e:
                out.append(f"    (scrape failed: {e})")
            out.append("")
        for r in organic[max_scrape:]:
            out.append(f"[{organic.index(r) + 1}] {r.get('title', '')}")
            out.append(f"    URL: {r.get('link', '')}")
            out.append(f"    Snippet: {r.get('snippet', '').strip()}")
            out.append("")
        return "\n".join(out)
    except Exception as e:
        return f"Deep search error: {e}"


# ──────────────────────────────────────────────
# OSINT (cached)
# ──────────────────────────────────────────────

import dns.resolver
import dns.exception


@cached(CACHE_TTL)
def dns_lookup(domain: str, record_type: str = "A", timeout: int = 8) -> str:
    try:
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            return f"Domain '{domain}' does not appear to resolve."
        resolver = dns.resolver.Resolver()
        resolver.nameservers = ["1.1.1.1", "8.8.8.8"]
        resolver.timeout = 10
        resolver.lifetime = 10
        answers = resolver.resolve(domain, record_type)
        if not answers:
            return f"No {record_type} records found for {domain}."
        out = [f"DNS {record_type} records for {domain}:"]
        for rdata in answers:
            out.append(f"  {rdata}")
        return "\n".join(out)
    except dns.resolver.NoAnswer:
        return f"No {record_type} records found for {domain}."
    except dns.resolver.NXDOMAIN:
        return f"Domain '{domain}' does not exist."
    except Exception as e:
        return f"DNS lookup error: {e}"


@cached(CACHE_TTL)
def whois_lookup(domain: str, timeout: int = 15) -> str:
    try:
        import whois
        w = whois.whois(domain)
        out_parts = [f"WHOIS for {domain}:"]
        for key in ["domain_name", "registrar", "whois_server", "creation_date",
                     "expiration_date", "updated_date", "name_servers", "status",
                     "emails", "org", "country", "city", "address", "name"]:
            val = w.get(key)
            if val:
                if isinstance(val, list):
                    val = ", ".join(str(v) for v in val)
                out_parts.append(f"  {key.replace('_', ' ').title()}: {val}")
        return "\n".join(out_parts) if len(out_parts) > 1 else f"No WHOIS data found for {domain}."
    except ImportError:
        return "WHOIS lookup unavailable (python-whois not installed)."
    except Exception as e:
        return f"WHOIS lookup error: {e}"


@cached(CACHE_TTL)
def ip_info(ip: str) -> str:
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=status,message,continent,country,regionName,city,district,zip,lat,lon,timezone,isp,org,as,asname,reverse,mobile,proxy,hosting,query",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "fail":
            return f"IP lookup failed: {data.get('message', 'unknown error')}"
        out = [f"IP Information for {data.get('query', ip)}:"]
        fields = [
            ("continent", "Continent"), ("country", "Country"), ("regionName", "Region"),
            ("city", "City"), ("district", "District"), ("zip", "Postal Code"),
            ("lat", "Latitude"), ("lon", "Longitude"), ("timezone", "Timezone"),
            ("isp", "ISP"), ("org", "Organization"), ("as", "ASN"), ("asname", "AS Name"),
            ("reverse", "Reverse DNS"), ("mobile", "Mobile"), ("proxy", "Proxy/VPN"),
            ("hosting", "Hosting"),
        ]
        for key, label in fields:
            val = data.get(key)
            if val is not None and val != "":
                out.append(f"  {label}: {val}")
        return "\n".join(out)
    except Exception as e:
        return f"IP lookup error: {e}"


@cached(CACHE_TTL)
def wayback_urls(domain: str, limit: int = 20, timeout: int = 15) -> str:
    try:
        resp = requests.get(
            "https://web.archive.org/cdx/search/cdx",
            params={
                "url": f"{domain}/*",
                "output": "json",
                "limit": limit,
                "fl": "timestamp,original",
                "collapse": "urlkey",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        rows = resp.json()
        if len(rows) < 2:
            return f"No Wayback Machine snapshots found for {domain}."
        out = [f"Wayback Machine snapshots for {domain} (showing {limit}):"]
        for row in rows[1:]:
            ts, url = row[0], row[1]
            date = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"
            out.append(f"  [{date}] {url}")
        return "\n".join(out)
    except Exception as e:
        return f"Wayback Machine lookup error: {e}"


# ──────────────────────────────────────────────
# Memory tools
# ──────────────────────────────────────────────

_memory_user_id: Optional[int] = None

def set_memory_user(user_id: Optional[int] = None):
    global _memory_user_id
    _memory_user_id = user_id

def memory_store(content: str, category: str = "general") -> str:
    from memory import store
    return store(content, category, user_id=_memory_user_id)

def memory_recall(limit: int = 15) -> str:
    from memory import recall
    memories = recall(user_id=_memory_user_id, limit=limit)
    if not memories:
        return "No memories saved yet."
    lines = [f"=== Saved Memories ({len(memories)}) ==="]
    for m in memories:
        lines.append(f"[{m['category']}] {m['content']} (saved {m['created']})")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Sandbox helpers
# ──────────────────────────────────────────────


def _require_sandbox():
    """Get the current user's sandbox or raise a clear error."""
    sb = get_sandbox()
    if sb is None:
        raise SandboxError(
            "No sandbox active. The agent must be initialized with a user context. "
            "Use `agent.py` which automatically sets up per-user sandboxes."
        )
    return sb


def _sandbox_ok() -> bool:
    """Check if sandbox is available (Docker running + sandbox enabled)."""
    if not SANDBOX_ENABLED:
        return False
    return is_docker_available()


# ──────────────────────────────────────────────
# Terminal (sandboxed)
# ──────────────────────────────────────────────


def terminal_execute(command: str) -> str:
    """Execute a shell command inside the user's Docker sandbox."""
    if not _sandbox_ok():
        return (
            "[BLOCKED] Docker sandbox is required but Docker is not available.\n"
            "Install Docker and try again."
        )
    try:
        sb = _require_sandbox()
        exit_code, stdout, stderr = sb.exec_run(command)
        out = f"[Sandbox | Exit code: {exit_code}]\n"
        if stdout:
            out += f"--- stdout ---\n{stdout}\n"
        if stderr:
            out += f"--- stderr ---\n{stderr}\n"
        if not stdout and not stderr:
            out += "(no output)\n"
        return out
    except SandboxError as e:
        return f"[BLOCKED] {e}"
    except Exception as e:
        return f"[ERROR] Command failed: {e}"


# ──────────────────────────────────────────────
# Python REPL (sandboxed)
# ──────────────────────────────────────────────


def python_execute(code: str, timeout: int = 30) -> str:
    """Execute Python code inside the user's Docker sandbox."""
    if not _sandbox_ok():
        return (
            "[BLOCKED] Docker sandbox is required but Docker is not available.\n"
            "Install Docker Desktop and try again."
        )
    try:
        sb = _require_sandbox()
        exit_code, stdout, stderr = sb.exec_python(code, timeout=timeout)
        out = f"[Python (sandbox) | Exit code: {exit_code}]\n"
        if stdout:
            out += f"--- stdout ---\n{stdout}\n"
        if stderr:
            out += f"--- stderr ---\n{stderr}\n"
        if not stdout and not stderr:
            out += "(no output)\n"
        return out
    except SandboxError as e:
        return f"[BLOCKED] {e}"
    except Exception as e:
        return f"[ERROR] Python execution failed: {e}"


# ──────────────────────────────────────────────
# File Management (sandbox-scoped)
# ──────────────────────────────────────────────

MAX_FILE_SIZE = 2_000_000
MAX_READ_LINES = 2000


def file_read(path: str, limit: int = 2000) -> str:
    sb = _require_sandbox()
    return sb.read_file(path, limit=limit)


def file_write(path: str, content: str, append: bool = False) -> str:
    sb = _require_sandbox()
    return sb.write_file(path, content, append=append)


def file_delete(path: str) -> str:
    sb = _require_sandbox()
    return sb.delete_file(path)


def file_exists(path: str) -> str:
    sb = _require_sandbox()
    return sb.file_exists(path)


def file_search(query: str, path: str = ".", include: str = "*") -> str:
    sb = _require_sandbox()
    search_dir = sb.abspath(path)
    if not os.path.isdir(search_dir):
        return f"Error: Not a directory: {path}"
    pattern = re.compile(query, re.IGNORECASE)
    matches = []
    try:
        glob_pattern = os.path.join(search_dir, "**", include)
        for filepath in glob.glob(glob_pattern, recursive=True):
            if not os.path.isfile(filepath):
                continue
            try:
                size = os.path.getsize(filepath)
                if size > MAX_FILE_SIZE:
                    continue
            except Exception:
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if i > MAX_READ_LINES:
                            break
                        if pattern.search(line):
                            rel = os.path.relpath(filepath, search_dir)
                            matches.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(matches) >= 100:
                                break
                if len(matches) >= 100:
                    break
            except Exception:
                continue
        if not matches:
            return f"No matches found for '{query}' in {path} (pattern: {include})"
        return f"Found {len(matches)} match(es) for '{query}':\n" + "\n".join(matches)
    except Exception as e:
        return f"Search error: {e}"


def dir_list(path: str = ".") -> str:
    sb = _require_sandbox()
    return sb.list_dir(path)


def dir_create(path: str) -> str:
    sb = _require_sandbox()
    return sb.create_dir(path)


def dir_delete(path: str) -> str:
    sb = _require_sandbox()
    return sb.delete_dir(path)


# ──────────────────────────────────────────────
# Tool dispatch
# ──────────────────────────────────────────────

# ──────────────────────────────────────────────
# Jikan (MyAnimeList) API
# ──────────────────────────────────────────────

JIKAN_BASE = "https://api.jikan.moe/v4"


def _jikan_get(endpoint: str, params: dict | None = None, timeout: int = 8) -> dict | None:
    """Make a Jikan API GET request with rate-limit handling."""
    for attempt in range(3):
        try:
            resp = requests.get(
                f"{JIKAN_BASE}/{endpoint}",
                params=params,
                timeout=timeout,
            )
            if resp.status_code == 429:
                retry = int(resp.headers.get("Retry-After", 1))
                import time
                time.sleep(retry + 0.5)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            if attempt == 2:
                return None
            import time
            time.sleep(1)
    return None


def _fmt_anime(a: dict) -> str:
    title = a.get("title", "?")
    score = a.get("score", "?")
    eps = a.get("episodes", "?")
    status = a.get("status", "?")
    rank = a.get("rank", "?")
    synopsis = (a.get("synopsis") or "")[:300]
    mal_id = a.get("mal_id", "?")
    lines = [
        f"[{mal_id}] {title}",
        f"  Score: {score}  |  Episodes: {eps}  |  Status: {status}  |  Rank: #{rank}",
    ]
    if synopsis:
        lines.append(f"  {synopsis}")
    return "\n".join(lines)


def _fmt_manga(m: dict) -> str:
    title = m.get("title", "?")
    score = m.get("score", "?")
    vols = m.get("volumes", "?")
    chs = m.get("chapters", "?")
    status = m.get("status", "?")
    rank = m.get("rank", "?")
    synopsis = (m.get("synopsis") or "")[:300]
    mal_id = m.get("mal_id", "?")
    lines = [
        f"[{mal_id}] {title}",
        f"  Score: {score}  |  Volumes: {vols}  |  Chapters: {chs}  |  Status: {status}  |  Rank: #{rank}",
    ]
    if synopsis:
        lines.append(f"  {synopsis}")
    return "\n".join(lines)


def anime_search(query: str, limit: int = 5, type: str = "", min_score: float = 0,
                 status: str = "", timeout: int = 8) -> str:
    params = {"q": query, "limit": min(limit, 25), "page": 1}
    if type:
        params["type"] = type
    if min_score > 0:
        params["min_score"] = min_score
    if status:
        params["status"] = status
    data = _jikan_get("anime", params, timeout=timeout)
    if not data:
        return "Anime search failed — API may be rate-limited."
    results = data.get("data", [])
    if not results:
        return f"No anime found for '{query}'."
    out = [f"Anime results for '{query}':"]
    for a in results[:limit]:
        out.append("")
        out.append(_fmt_anime(a))
    return "\n".join(out)


def anime_get(mal_id: int, timeout: int = 8) -> str:
    data = _jikan_get(f"anime/{mal_id}/full", timeout=timeout)
    if not data:
        return f"Could not fetch anime #{mal_id}."
    a = data.get("data", {})
    if not a:
        return f"Anime #{mal_id} not found."
    title = a.get("title", "?")
    title_jp = a.get("title_japanese", "")
    title_en = a.get("title_english", "")
    score = a.get("score", "?")
    scored_by = a.get("scored_by", "?")
    rank = a.get("rank", "?")
    popularity = a.get("popularity", "?")
    eps = a.get("episodes", "?")
    status = a.get("status", "?")
    aired = a.get("aired", {}).get("string", "?")
    rating = a.get("rating", "?")
    synopsis = a.get("synopsis", "") or "No synopsis."
    season = a.get("season", "")
    year = a.get("year", "")
    genres = [g["name"] for g in a.get("genres", [])]
    studios = [s["name"] for s in a.get("studios", [])]
    producers = [p["name"] for p in a.get("producers", [])]
    source = a.get("source", "?")
    duration = a.get("duration", "?")
    trailer = a.get("trailer", {}).get("url", "")
    mal_url = a.get("url", "")

    lines = [
        f"# {title}",
    ]
    if title_en and title_en != title:
        lines.append(f"English: {title_en}")
    if title_jp:
        lines.append(f"Japanese: {title_jp}")
    lines.append("")
    lines.append(f"Score: {score} (by {scored_by} users)  |  Rank: #{rank}  |  Popularity: #{popularity}")
    lines.append(f"Episodes: {eps}  |  Status: {status}  |  Rating: {rating}")
    lines.append(f"Aired: {aired}  |  Season: {season} {year}")
    lines.append(f"Source: {source}  |  Duration: {duration}")
    if genres:
        lines.append(f"Genres: {', '.join(genres)}")
    if studios:
        lines.append(f"Studios: {', '.join(studios)}")
    if producers:
        lines.append(f"Producers: {', '.join(producers)}")
    lines.append("")
    lines.append(synopsis[:1000])
    if mal_url:
        lines.append(f"\nMAL: {mal_url}")
    if trailer:
        lines.append(f"Trailer: {trailer}")
    return "\n".join(lines)


def anime_top(limit: int = 5, type: str = "", filter: str = "", timeout: int = 8) -> str:
    params = {"limit": min(limit, 25), "page": 1}
    if type:
        params["type"] = type
    if filter:
        params["filter"] = filter
    data = _jikan_get("top/anime", params, timeout=timeout)
    if not data:
        return "Failed to fetch top anime."
    results = data.get("data", [])
    if not results:
        return "No top anime results."
    label = "Top Anime"
    if filter == "airing":
        label = "Currently Airing (Top)"
    elif filter == "upcoming":
        label = "Upcoming Anime (Top)"
    elif filter == "bypopularity":
        label = "Most Popular Anime"
    elif filter == "favorite":
        label = "Most Favorited Anime"
    out = [f"{label}:"]
    for a in results[:limit]:
        out.append("")
        out.append(_fmt_anime(a))
    return "\n".join(out)


def anime_seasonal(limit: int = 5, filter: str = "", timeout: int = 8) -> str:
    params = {"limit": min(limit, 25), "page": 1}
    if filter:
        params["filter"] = filter
    data = _jikan_get("seasons/now", params, timeout=timeout)
    if not data:
        return "Failed to fetch seasonal anime."
    results = data.get("data", [])
    if not results:
        return "No seasonal anime found."
    out = [f"Currently Airing ({len(results)} titles):"]
    for a in results[:limit]:
        out.append("")
        out.append(_fmt_anime(a))
    return "\n".join(out)


def manga_search(query: str, limit: int = 5, type: str = "", status: str = "", timeout: int = 8) -> str:
    params = {"q": query, "limit": min(limit, 25), "page": 1}
    if type:
        params["type"] = type
    if status:
        params["status"] = status
    data = _jikan_get("manga", params, timeout=timeout)
    if not data:
        return "Manga search failed — API may be rate-limited."
    results = data.get("data", [])
    if not results:
        return f"No manga found for '{query}'."
    out = [f"Manga results for '{query}':"]
    for m in results[:limit]:
        out.append("")
        out.append(_fmt_manga(m))
    return "\n".join(out)


def anime_random() -> str:
    data = _jikan_get("random/anime")
    if not data:
        return "Failed to fetch random anime."
    a = data.get("data", {})
    if not a:
        return "No random anime returned."
    title = a.get("title", "?")
    mal_id = a.get("mal_id", "?")
    score = a.get("score", "?")
    synopsis = (a.get("synopsis") or "")[:300]
    mal_url = a.get("url", "")
    return (
        f"🎲 Random Anime: {title} [#{mal_id}]\n"
        f"Score: {score}  |  MAL: {mal_url}\n"
        f"{synopsis}"
    )

def gfn(region: str = "", timeout: int = 8) -> str:
    """Check NVIDIA GeForce NOW queue positions."""
    try:
        resp = requests.get("https://api.printedwaste.com/gfn/queue", timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("status"):
            return f"GFN API error: {data.get('errors', 'unknown')}"
        servers = data.get("data", {})
        if not servers:
            return "No server data returned."
        items = []
        for sid, info in sorted(servers.items()):
            r = info.get("Region", "")
            if region and r.upper() != region.upper():
                continue
            pos = info.get("QueuePosition", "?")
            eta_ms = info.get("eta")
            ts = info.get("Last Updated", 0)
            updated = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"
            eta_str = ""
            if eta_ms is not None and isinstance(eta_ms, (int, float)) and eta_ms > 0:
                mins = eta_ms // 60000
                secs = (eta_ms % 60000) // 1000
                eta_str = f" ~{mins}m{secs}s"
            pos_str = "No queue" if pos == 0 else f"#{pos}"
            items.append(f"  {sid:25s}  {pos_str:8s}{eta_str:12s}  {r:6s}  {updated}")
        if not items:
            return f"No servers found for region '{region}'."
        summary = (
            f"GFN Queue Status ({len(items)} servers)"
            + (" — " + region if region else "")
            + f"\n{'Server':25s}  {'Queue':8s}  {'ETA':12s}  {'Region':6s}  {'Updated'}\n"
            + "\n".join(items)
        )
        return summary
    except Exception as e:
        return f"GFN check error: {e}"


# ──────────────────────────────────────────────
# Free utility tools (no API keys required)
# ──────────────────────────────────────────────


def wikipedia(query: str) -> str:
    try:
        headers = {"User-Agent": "Charlyn/1.0 (AI Assistant)"}
        search_resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={"action": "opensearch", "search": query, "limit": 5, "format": "json"},
            headers=headers,
            timeout=8,
        )
        search_resp.raise_for_status()
        search_data = search_resp.json()
        titles = search_data[1]
        if not titles:
            return f"No Wikipedia results found for '{query}'."
        title = titles[0]
        summary_resp = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{url_quote(title)}",
            headers=headers,
            timeout=8,
        )
        summary_resp.raise_for_status()
        data = summary_resp.json()
        extract = (data.get("extract") or "")[:500]
        page_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
        return (
            f"Title: {data.get('title', title)}\n"
            f"URL: {page_url}\n\n"
            f"{extract}"
        )
    except Exception as e:
        return f"Wikipedia lookup error: {e}"


def hackernews(limit: int = 10, type: str = "top") -> str:
    try:
        type_map = {"top": "topstories", "new": "newstories", "best": "beststories"}
        endpoint = type_map.get(type, "topstories")
        resp = requests.get(f"https://hacker-news.firebaseio.com/v0/{endpoint}.json", timeout=10)
        resp.raise_for_status()
        ids = resp.json()[:min(limit, 30)]
        results = []
        for i, story_id in enumerate(ids):
            try:
                item_resp = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json",
                    timeout=10,
                )
                item_resp.raise_for_status()
                item = item_resp.json()
                title = item.get("title", "?")
                score = item.get("score", "?")
                by = item.get("by", "?")
                url = item.get("url", f"https://news.ycombinator.com/item?id={story_id}")
                comments = item.get("descendants", 0)
                results.append(f"{i+1}. {title}\n   Score: {score} | By: {by} | Comments: {comments}\n   {url}")
            except Exception:
                continue
        if not results:
            return "No stories found."
        return f"Hacker News {type} stories:\n" + "\n\n".join(results)
    except Exception as e:
        return f"Hacker News error: {e}"


def yt_transcript(video_id: str) -> str:
    try:
        vid = video_id
        if "youtube.com" in video_id or "youtu.be" in video_id:
            parsed = urlparse(video_id)
            if parsed.hostname == "youtu.be":
                vid = parsed.path.lstrip("/")
            else:
                qs = parse_qs(parsed.query)
                vid = qs.get("v", [None])[0]
            if not vid:
                return "Could not extract video ID from URL."
        resp = requests.get(f"https://youtubetranscript.com/api?video_id={vid}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            text = " ".join(s.get("text", "") for s in data)
        elif isinstance(data, dict):
            text = data.get("text", str(data))
        else:
            text = str(data)
        text = text[:2000]
        return f"Transcript for video {vid}:\n\n{text}"
    except Exception as e:
        return f"YouTube transcript error: {e}"


def github_search(query: str, limit: int = 5) -> str:
    try:
        resp = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": min(limit, 10)},
            headers={"User-Agent": "Charlyn/1.0"},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return f"No GitHub repositories found for '{query}'."
        results = []
        for i, repo in enumerate(items[:min(limit, 10)], 1):
            name = repo.get("full_name", "?")
            desc = repo.get("description") or "No description"
            stars = repo.get("stargazers_count", 0)
            lang = repo.get("language") or "N/A"
            url = repo.get("html_url", "")
            results.append(f"{i}. {name}\n   Stars: {stars} | Language: {lang}\n   {desc}\n   {url}")
        return "GitHub Search Results:\n" + "\n\n".join(results)
    except Exception as e:
        return f"GitHub search error: {e}"


def define_word(word: str) -> str:
    try:
        resp = requests.get(
            f"https://api.dictionaryapi.dev/api/v2/entries/en/{url_quote(word)}",
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        entry = data[0]
        word = entry.get("word", "?")
        phonetic = entry.get("phonetic") or entry.get("phonetics", [{}])[0].get("text", "")
        meanings = entry.get("meanings", [])
        lines = [f"Word: {word}"]
        if phonetic:
            lines.append(f"Phonetic: {phonetic}")
        for m in meanings:
            pos = m.get("partOfSpeech", "?")
            defs = m.get("definitions", [])
            for d in defs[:2]:
                definition = d.get("definition", "")
                example = d.get("example", "")
                lines.append(f"\n[{pos}] {definition}")
                if example:
                    lines.append(f"  Example: {example}")
        return "\n".join(lines)
    except Exception as e:
        return f"Dictionary lookup error: {e}"


def reddit_search(query: str, limit: int = 5, subreddit: str = "") -> str:
    try:
        if subreddit:
            url = f"https://old.reddit.com/r/{subreddit}/search.json"
        else:
            url = "https://old.reddit.com/search.json"
        params = {"q": query, "limit": min(limit, 10)}
        if subreddit:
            params["restrict_sr"] = "on"
        resp = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Charlyn/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        children = data.get("data", {}).get("children", [])
        if not children:
            return f"No Reddit results for '{query}'."
        results = []
        for i, child in enumerate(children[:min(limit, 10)], 1):
            post = child.get("data", {})
            title = post.get("title", "?")
            sub = post.get("subreddit", "?")
            score = post.get("score", 0)
            comments = post.get("num_comments", 0)
            permalink = post.get("permalink", "")
            full_url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
            results.append(f"{i}. {title}\n   r/{sub} | Score: {score} | Comments: {comments}\n   {full_url}")
        return "Reddit Search Results:\n" + "\n\n".join(results)
    except Exception as e:
        return f"Reddit search error: {e}"


def qr_encode(data: str) -> str:
    try:
        import qrcode
        img = qrcode.make(data)
        hash_digest = hashlib.md5(data.encode()).hexdigest()[:8]
        path = os.path.join(SCREENSHOTS_DIR, f"qr_{hash_digest}.png")
        img.save(path)
        return f"QR code saved to {path}"
    except ImportError:
        return "QR code generation unavailable (qrcode module not installed)."
    except Exception as e:
        return f"QR code error: {e}"


def uuid_gen(count: int = 1, version: int = 4) -> str:
    try:
        uuids = []
        for _ in range(min(count, 10)):
            if version == 1:
                uuids.append(str(uuid.uuid1()))
            else:
                uuids.append(str(uuid.uuid4()))
        return "Generated UUIDs:\n" + "\n".join(f"  {u}" for u in uuids)
    except Exception as e:
        return f"UUID generation error: {e}"


def hash_text(text: str, algorithm: str = "sha256") -> str:
    try:
        algo_map = {
            "md5": hashlib.md5,
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
        }
        h = algo_map.get(algorithm, hashlib.sha256)(text.encode())
        return f"{algorithm.upper()} hash: {h.hexdigest()}"
    except Exception as e:
        return f"Hashing error: {e}"


def ssl_check(domain: str, port: int = 443) -> str:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((domain, port), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                issuer = dict(x[0] for x in cert.get("issuer", []))
                subject = dict(x[0] for x in cert.get("subject", []))
                not_after = cert.get("notAfter", "?")
                expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days_left = (expires - datetime.now()).days
                return (
                    f"SSL Certificate for {domain}:{port}\n"
                    f"  Subject: {subject.get('commonName', '?')}\n"
                    f"  Issuer: {issuer.get('commonName', '?')}\n"
                    f"  Expires: {not_after}\n"
                    f"  Days left: {days_left}"
                )
    except Exception as e:
        return f"SSL check error: {e}"


def http_headers(url: str, follow_redirects: bool = True) -> str:
    try:
        resp = requests.head(url, allow_redirects=follow_redirects, timeout=10)
        lines = [f"HTTP Headers for {url}", f"Status: {resp.status_code} {resp.reason}"]
        for key, val in resp.headers.items():
            lines.append(f"  {key}: {val}")
        return "\n".join(lines)
    except Exception as e:
        return f"HTTP headers error: {e}"


def joke(category: str = "any") -> str:
    try:
        cat = category.capitalize() if category != "any" else "Any"
        resp = requests.get(
            f"https://v2.jokeapi.dev/joke/{cat}",
            params={"safe-mode": ""},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            return f"Joke API error: {data.get('message', 'unknown')}"
        if data.get("type") == "single":
            return data.get("joke", "No joke found.")
        return f"{data.get('setup', '')}\n{data.get('delivery', '')}"
    except Exception as e:
        return f"Joke error: {e}"


def quote(tag: str = "") -> str:
    try:
        params = {}
        if tag:
            params["tags"] = tag
        resp = requests.get("https://api.quotable.io/random", params=params, timeout=8)
        resp.raise_for_status()
        data = resp.json()
        return f'"{data.get("content", "")}"\n— {data.get("author", "Unknown")}'
    except Exception:
        pass
    try:
        resp = requests.get("https://zenquotes.io/api/random", timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            q = data[0]
            return f'"{q.get("q", "")}"\n— {q.get("a", "Unknown")}'
        return f'"{data.get("q", "")}"\n— {data.get("a", "Unknown")}'
    except Exception as e:
        return f"Quote error: {e}"


def lyrics(artist: str, title: str) -> str:
    try:
        resp = requests.get(
            f"https://api.lyrics.ovh/v1/{url_quote(artist)}/{url_quote(title)}",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        lyrics_text = data.get("lyrics", "")
        if not lyrics_text:
            return f"No lyrics found for '{title}' by {artist}."
        if len(lyrics_text) > 2000:
            lyrics_text = lyrics_text[:2000] + "\n\n[truncated]"
        return f"Lyrics for '{title}' by {artist}:\n\n{lyrics_text}"
    except Exception as e:
        return f"Lyrics lookup error: {e}"


def color_picker(color: str) -> str:
    try:
        color = color.strip().lower()
        r = g = b = 0
        if color.startswith("#"):
            hex_val = color.lstrip("#")
            if len(hex_val) == 3:
                hex_val = "".join(c * 2 for c in hex_val)
            if len(hex_val) == 6:
                r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
            else:
                return f"Invalid hex color: {color}"
        elif color.startswith("rgb"):
            parts = [int(x.strip()) for x in color.strip("rgb() ").split(",")]
            r, g, b = parts[0], parts[1], parts[2]
        elif color.startswith("hsl"):
            parts = [float(x.strip()) for x in color.strip("hsl() ").split(",")]
            h, s, l = parts[0], parts[1] / 100, parts[2] / 100
            c_val = (1 - abs(2 * l - 1)) * s
            x = c_val * (1 - abs((h / 60) % 2 - 1))
            m = l - c_val / 2
            if h < 60:
                r, g, b = c_val, x, 0
            elif h < 120:
                r, g, b = x, c_val, 0
            elif h < 180:
                r, g, b = 0, c_val, x
            elif h < 240:
                r, g, b = 0, x, c_val
            elif h < 300:
                r, g, b = x, 0, c_val
            else:
                r, g, b = c_val, 0, x
            r, g, b = int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
        else:
            return f"Unrecognized color format: {color}. Use hex (#ff0000), rgb(r,g,b), or hsl(h,s,l)."

        hex_out = f"#{r:02x}{g:02x}{b:02x}"
        rgb_out = f"rgb({r},{g},{b})"

        rn, gn, bn = r / 255, g / 255, b / 255
        mx, mn = max(rn, gn, bn), min(rn, gn, bn)
        l_val = (mx + mn) / 2
        if mx == mn:
            h = s_val = 0
        else:
            d = mx - mn
            s_val = d / (1 - abs(2 * l_val - 1))
            if mx == rn:
                h = 60 * (((gn - bn) / d) % 6)
            elif mx == gn:
                h = 60 * (((bn - rn) / d) + 2)
            else:
                h = 60 * (((rn - gn) / d) + 4)
        hsl_out = f"hsl({h:.0f},{s_val * 100:.0f},{l_val * 100:.0f})"

        comp1_h = (h + 180) % 360
        comp2_h = (h + 90) % 360
        comp1 = f"hsl({comp1_h:.0f},{s_val * 100:.0f},{l_val * 100:.0f})"
        comp2 = f"hsl({comp2_h:.0f},{s_val * 100:.0f},{l_val * 100:.0f})"

        return (
            f"Color: {hex_out}\n"
            f"  RGB: {rgb_out}\n"
            f"  HSL: {hsl_out}\n"
            f"  Complementary: {comp1}, {comp2}"
        )
    except Exception as e:
        return f"Color conversion error: {e}"


def weather(location: str, timeout: int = 8) -> str:
    """Get current weather via Open-Meteo (free, no key)."""
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": location, "count": 1, "language": "en", "format": "json"},
            timeout=timeout,
        )
        geo.raise_for_status()
        geo_data = geo.json()
        results = geo_data.get("results", [])
        if not results:
            return f"Location '{location}' not found."
        r = results[0]
        lat, lon = r["latitude"], r["longitude"]
        name = f"{r.get('name', location)}, {r.get('country', '')}"

        w = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto",
            },
            timeout=timeout,
        )
        w.raise_for_status()
        wdata = w.json()
        c = wdata.get("current", {})
        temp = c.get("temperature_2m", "?")
        feels = c.get("apparent_temperature", "?")
        humidity = c.get("relative_humidity_2m", "?")
        precip = c.get("precipitation", 0)
        wind = c.get("wind_speed_10m", "?")
        code = c.get("weather_code", 0)
        conditions = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        cond = conditions.get(code, f"Code {code}")
        return (
            f"Weather for {name}\n"
            f"  Condition: {cond}\n"
            f"  Temperature: {temp}°C (feels like {feels}°C)\n"
            f"  Humidity: {humidity}%\n"
            f"  Precipitation: {precip} mm\n"
            f"  Wind: {wind} km/h"
        )
    except requests.RequestException as e:
        return f"Weather lookup error: {e}"
    except Exception as e:
        return f"Weather lookup error: {e}"


def exchange_rate(base: str = "USD", target: str = "", timeout: int = 8) -> str:
    """Get exchange rates via open.er-api.com."""
    try:
        resp = requests.get(
            f"https://open.er-api.com/v6/latest/{url_quote(base.upper())}",
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("rates"):
            return f"Could not get rates for {base}."
        rates = data["rates"]
        if target:
            target = target.upper()
            if target in rates:
                return f"1 {base.upper()} = {rates[target]} {target}"
            return f"Currency '{target}' not found."
        majors = ["USD", "EUR", "GBP", "JPY", "CNY", "THB", "AUD", "CAD", "CHF", "INR", "KRW", "SGD"]
        lines = [f"Exchange rates (base: {base.upper()}):"]
        for code in majors:
            if code != base.upper() and code in rates:
                lines.append(f"  {code}: {rates[code]:.4f}")
        return "\n".join(lines)
    except Exception as e:
        return f"Exchange rate error: {e}"


def country_info(name: str, timeout: int = 8) -> str:
    """Get country info via restcountries.com."""
    try:
        resp = requests.get(
            f"https://restcountries.com/v3.1/name/{url_quote(name)}",
            timeout=timeout,
        )
        if resp.status_code == 404:
            return f"Country '{name}' not found."
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return f"Country '{name}' not found."
        c = data[0]
        common = c.get("name", {}).get("common", "?")
        official = c.get("name", {}).get("official", "")
        capital = ", ".join(c.get("capital", [])) or "?"
        region = c.get("region", "?")
        subregion = c.get("subregion", "") or ""
        population = f"{c.get('population', 0):,}"
        area = f"{c.get('area', 0):,} km²"
        languages = ", ".join(c.get("languages", {}).values()) or "?"
        currencies = ", ".join(
            f"{v['name']} ({v.get('symbol', '')})"
            for v in c.get("currencies", {}).values()
        ) or "?"
        timezones = ", ".join(c.get("timezones", [])[:3]) or "?"
        flag = c.get("flag", "")
        tld = ", ".join(c.get("tld", [])) or "?"
        return (
            f"{flag} {common}\n"
            f"  Official: {official}\n"
            f"  Capital: {capital}\n"
            f"  Region: {region} ({subregion})" if subregion else f"  Region: {region}"
            f"\n  Population: {population}"
            f"\n  Area: {area}"
            f"\n  Languages: {languages}"
            f"\n  Currencies: {currencies}"
            f"\n  Timezone: {timezones}"
            f"\n  TLD: {tld}"
        )
    except Exception as e:
        return f"Country info error: {e}"


def tv_search(query: str, timeout: int = 8) -> str:
    """Search TV shows/movies via tvmaze.com."""
    try:
        resp = requests.get(
            f"https://api.tvmaze.com/search/shows?q={url_quote(query)}",
            timeout=timeout,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return f"No shows found for '{query}'."
        out = [f"TV results for '{query}':"]
        for r in results[:5]:
            s = r.get("show", {})
            name = s.get("name", "?")
            status = s.get("status", "?")
            genres = ", ".join(s.get("genres", [])) or "?"
            rating = s.get("rating", {}).get("average", "?")
            network = s.get("network", {})
            net_name = network.get("name", "") if network else ""
            url = s.get("url", "")
            summary = (s.get("summary") or "")[:200]
            summary = summary.replace("<p>", "").replace("</p>", "").replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", "")
            lang = s.get("language", "?")
            premiered = s.get("premiered", "?")
            runtime = s.get("runtime", "?")
            out.append("")
            out.append(f"{name} | Rating: {rating} | Status: {status}")
            out.append(f"  Genres: {genres} | Language: {lang}")
            out.append(f"  Premiered: {premiered}" + (f" | Network: {net_name}" if net_name else ""))
            if summary:
                out.append(f"  {summary}")
        return "\n".join(out)
    except Exception as e:
        return f"TV search error: {e}"


# ──────────────────────────────────────────────
# Timer / Reminder tools
# ──────────────────────────────────────────────


def set_timer(duration: str, message: str) -> str:
    """Set a timer/reminder that fires after a duration."""
    from timers import timer_manager
    uid = _memory_user_id or 0
    timer_id, seconds = timer_manager.set_timer(uid, duration, message)
    friendly = _fmt_duration(seconds)
    return (
        f"Timer set! ⏰\n"
        f"  ID: {timer_id}\n"
        f"  Duration: {friendly}\n"
        f"  Message: {message}\n"
        f"You'll be notified when time is up."
    )


def cancel_timer(timer_id: str) -> str:
    from timers import timer_manager
    if timer_manager.cancel_timer(timer_id):
        return f"Timer {timer_id} cancelled."
    return f"Timer {timer_id} not found."


def timer_list() -> str:
    from timers import timer_manager
    uid = _memory_user_id or 0
    timers = timer_manager.list_timers(uid)
    if not timers:
        return "No active timers."
    lines = [f"Active Timers ({len(timers)}):"]
    for t in timers:
        remaining = _fmt_duration(t["remaining_seconds"])
        lines.append(f"  [{t['id']}] {t['message']} — {remaining} left")
    return "\n".join(lines)


def _fmt_duration(total_seconds: int) -> str:
    parts = []
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


# ──────────────────────────────────────────────
# VM (QEMU + VNC) control
# ──────────────────────────────────────────────


def vm_mouse_move(x: int, y: int) -> str:
    try:
        vnc_ctl.move(x, y)
        return f"Moved mouse to ({x}, {y})."
    except Exception as e:
        return f"VM mouse move error: {e}"


def vm_click(x: int, y: int, button: int = 1) -> str:
    try:
        vnc_ctl.click(x, y, button)
        btn = {1: "left", 2: "middle", 3: "right"}.get(button, str(button))
        return f"Clicked {btn} at ({x}, {y})."
    except Exception as e:
        return f"VM click error: {e}"


def vm_type(text: str) -> str:
    try:
        vnc_ctl.type_text(text)
        return f"Typed: {text[:200]}" + ("..." if len(text) > 200 else "")
    except Exception as e:
        return f"VM type error: {e}"


def vm_key(key: str) -> str:
    try:
        vnc_ctl.key_press(key)
        return f"Pressed key: {key}"
    except Exception as e:
        return f"VM key error: {e}"


def vm_screenshot() -> str:
    try:
        data = vnc_ctl.screenshot()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"vm_screenshot_{ts}.png")
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        return f"VM screenshot error: {e}"


def vm_find_text(text: str) -> str:
    """Find text on the VM screen and return its coordinates plus all visible text."""
    try:
        data = vnc_ctl.screenshot()
        img = Image.open(io.BytesIO(data))
        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        all_words = []
        matches = []
        for i in range(len(ocr_data["text"])):
            word = ocr_data["text"][i].strip()
            if not word:
                continue
            x = ocr_data["left"][i]
            y = ocr_data["top"][i]
            w = ocr_data["width"][i]
            h = ocr_data["height"][i]
            conf = ocr_data["conf"][i]
            all_words.append({"word": word, "x": x, "y": y, "w": w, "h": h, "conf": conf})
            if text.lower() in word.lower():
                matches.append({"word": word, "x": x, "y": y, "w": w, "h": h, "conf": conf})

        out = [f"Screen text ({len(all_words)} words):"]
        # Build a rough text layout from sorted words
        lines = {}
        for w in all_words:
            line_key = w["y"] // 20
            lines.setdefault(line_key, []).append(w)
        for line_y in sorted(lines):
            line_words = sorted(lines[line_y], key=lambda w: w["x"])
            line_text = " ".join(w["word"] for w in line_words)
            out.append(f"  y~{line_y*20}: {line_text}")

        if matches:
            out.append("")
            out.append(f"Matches for '{text}':")
            for m in matches:
                cx = m["x"] + m["w"] // 2
                cy = m["y"] + m["h"] // 2
                out.append(f"  '{m['word']}' at ({cx}, {cy})  [{m['x']},{m['y']} {m['w']}x{m['h']}] conf={m['conf']}%")
        else:
            out.append(f"\nNo matches for '{text}'.")

        return "\n".join(out)
    except Exception as e:
        return f"VM find text error: {e}"


def vm_terminal(command: str, timeout: int = 30) -> str:
    """Run a shell command inside the VM via SSH."""
    try:
        from config import VM_SSH_HOST, VM_SSH_PORT, VM_SSH_USER, VM_SSH_KEY
        import subprocess
        ssh_cmd = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            "-o", "LogLevel=ERROR",
            "-p", str(VM_SSH_PORT),
            "-i", VM_SSH_KEY,
            f"{VM_SSH_USER}@{VM_SSH_HOST}",
            command,
        ]
        r = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        out = f"[VM | Exit code: {r.returncode}]\n"
        if r.stdout:
            out += f"--- stdout ---\n{r.stdout}\n"
        if r.stderr:
            out += f"--- stderr ---\n{r.stderr}\n"
        if not r.stdout and not r.stderr:
            out += "(no output)"
        return out.strip()
    except subprocess.TimeoutExpired:
        return f"[VM] Command timed out after {timeout}s."
    except Exception as e:
        return f"[VM] SSH error: {e}"


def vm_click_text(text: str) -> str:
    """Find text on the VM screen and click at its center."""
    try:
        data = vnc_ctl.screenshot()
        img = Image.open(io.BytesIO(data))
        ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        best = None
        best_conf = 0
        for i in range(len(ocr_data["text"])):
            word = ocr_data["text"][i].strip()
            if not word:
                continue
            if text.lower() == word.lower():
                conf = ocr_data["conf"][i]
                if conf > best_conf:
                    best_conf = conf
                    best = {
                        "word": word,
                        "x": ocr_data["left"][i],
                        "y": ocr_data["top"][i],
                        "w": ocr_data["width"][i],
                        "h": ocr_data["height"][i],
                    }
        if not best:
            return f"Text '{text}' not found on screen."

        cx = best["x"] + best["w"] // 2
        cy = best["y"] + best["h"] // 2
        vnc_ctl.move(cx, cy)
        vnc_ctl.click(cx, cy)
        return f"Clicked '{best['word']}' at ({cx}, {cy}) (conf={best_conf}%)."
    except Exception as e:
        return f"VM click text error: {e}"


def execute_tool(call, browser: BrowserTool) -> str:
    name = call.name
    params = call.params

    if name == "browser_navigate":
        return browser.navigate(params.get("url", ""))
    elif name == "browser_click":
        return browser.click(params.get("selector", ""))
    elif name == "browser_type":
        return browser.type_text(params.get("selector", ""), params.get("text", ""))
    elif name == "browser_screenshot":
        return browser.screenshot()
    elif name == "ocr_analyze":
        return ocr_analyze(params.get("image_path", ""))
    elif name == "web_search":
        return web_search(params.get("query", ""), params.get("gl", SEARCH_REGION), params.get("timeout", 8))
    elif name == "web_scrape":
        return web_scrape(params.get("url", ""), params.get("timeout", 15))
    elif name == "web_deep_search":
        return web_deep_search(params.get("query", ""), params.get("gl", SEARCH_REGION), params.get("max_scrape", 3), params.get("timeout", 15))
    elif name == "username_search":
        return username_search(params.get("username", ""), params.get("timeout", 15))
    elif name == "dns_lookup":
        return dns_lookup(params.get("domain", ""), params.get("record_type", "A"), params.get("timeout", 8))
    elif name == "whois_lookup":
        return whois_lookup(params.get("domain", ""), params.get("timeout", 15))
    elif name == "ip_info":
        return ip_info(params.get("ip", ""))
    elif name == "wayback_urls":
        return wayback_urls(params.get("domain", ""), params.get("limit", 20), params.get("timeout", 15))
    elif name == "terminal":
        return terminal_execute(params.get("command", ""))
    elif name == "python_execute":
        return python_execute(params.get("code", ""), params.get("timeout", 30))
    elif name == "memory_store":
        return memory_store(params.get("content", ""), params.get("category", "general"))
    elif name == "memory_recall":
        return memory_recall(params.get("limit", 15))
    elif name == "file_read":
        return file_read(params.get("path", ""), params.get("limit", 2000))
    elif name == "file_write":
        return file_write(params.get("path", ""), params.get("content", ""), params.get("append", False))
    elif name == "file_delete":
        return file_delete(params.get("path", ""))
    elif name == "file_exists":
        return file_exists(params.get("path", ""))
    elif name == "file_search":
        return file_search(params.get("query", ""), params.get("path", "."), params.get("include", "*"))
    elif name == "dir_list":
        return dir_list(params.get("path", "."))
    elif name == "dir_create":
        return dir_create(params.get("path", ""))
    elif name == "dir_delete":
        return dir_delete(params.get("path", ""))
    elif name == "gfn":
        return gfn(params.get("region", ""), params.get("timeout", 8))
    elif name == "anime_search":
        return anime_search(
            params.get("query", ""),
            params.get("limit", 5),
            params.get("type", ""),
            params.get("min_score", 0),
            params.get("status", ""),
            params.get("timeout", 8),
        )
    elif name == "anime_get":
        return anime_get(params.get("mal_id", 0), params.get("timeout", 8))
    elif name == "anime_top":
        return anime_top(
            params.get("limit", 5),
            params.get("type", ""),
            params.get("filter", ""),
            params.get("timeout", 8),
        )
    elif name == "anime_seasonal":
        return anime_seasonal(
            params.get("limit", 5),
            params.get("filter", ""),
            params.get("timeout", 8),
        )
    elif name == "manga_search":
        return manga_search(
            params.get("query", ""),
            params.get("limit", 5),
            params.get("type", ""),
            params.get("status", ""),
            params.get("timeout", 8),
        )
    elif name == "anime_random":
        return anime_random()
    elif name == "wikipedia":
        return wikipedia(params.get("query", ""))
    elif name == "hackernews":
        return hackernews(params.get("limit", 10), params.get("type", "top"))
    elif name == "yt_transcript":
        return yt_transcript(params.get("video_id", ""))
    elif name == "github_search":
        return github_search(params.get("query", ""), params.get("limit", 5))
    elif name == "define_word":
        return define_word(params.get("word", ""))
    elif name == "reddit_search":
        return reddit_search(params.get("query", ""), params.get("limit", 5), params.get("subreddit", ""))
    elif name == "qr_encode":
        return qr_encode(params.get("data", ""))
    elif name == "uuid_gen":
        return uuid_gen(params.get("count", 1), params.get("version", 4))
    elif name == "hash_text":
        return hash_text(params.get("text", ""), params.get("algorithm", "sha256"))
    elif name == "ssl_check":
        return ssl_check(params.get("domain", ""), params.get("port", 443))
    elif name == "http_headers":
        return http_headers(params.get("url", ""), params.get("follow_redirects", True))
    elif name == "joke":
        return joke(params.get("category", "any"))
    elif name == "quote":
        return quote(params.get("tag", ""))
    elif name == "lyrics":
        return lyrics(params.get("artist", ""), params.get("title", ""))
    elif name == "color_picker":
        return color_picker(params.get("color", ""))
    elif name == "weather":
        return weather(params.get("location", ""), params.get("timeout", 8))
    elif name == "exchange_rate":
        return exchange_rate(
            params.get("base", "USD"),
            params.get("target", ""),
            params.get("timeout", 8),
        )
    elif name == "country_info":
        return country_info(params.get("name", ""), params.get("timeout", 8))
    elif name == "tv_search":
        return tv_search(params.get("query", ""), params.get("timeout", 8))
    elif name == "set_timer":
        return set_timer(params.get("duration", ""), params.get("message", ""))
    elif name == "cancel_timer":
        return cancel_timer(params.get("timer_id", ""))
    elif name == "timer_list":
        return timer_list()
    elif name == "anime_download":
        return video_anime_download(params.get("anime_name", ""))
    elif name == "video_upload":
        file_path = params.get("file_path", "")
        title = params.get("title", "Untitled")
        import os
        if not os.path.exists(file_path):
            return f"File not found: {file_path}"
        ext = os.path.splitext(file_path)[1].lower()
        content_type_map = {
            ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
            ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        }
        content_type = content_type_map.get(ext, "video/mp4")
        sto = video_upload_to_storage_to(file_path)
        if not sto:
            return f"storage.to upload failed for {title}"
        size = os.path.getsize(file_path)
        from video import get_video_duration
        duration = get_video_duration(file_path)
        watch_url = video_register_with_worker(
            title=title,
            storage_url=sto.get("url", ""),
            raw_url=sto.get("raw_url", ""),
            content_type=content_type,
            size=size,
            duration=int(duration) if duration else 0,
            part=params.get("part", 1),
            total_parts=params.get("total_parts", 1),
        )
        return (
            f"{title}\n"
            f"Size: {size / (1024*1024):.1f} MB\n"
            f"Watch: {watch_url}\n"
            f"Direct: {sto.get('raw_url', '')}\n"
            f"Download page: {sto.get('url', '')}"
        )
    elif name == "anime_download_and_upload":
        return video_download_and_upload(params.get("anime_name", ""))
    elif name == "publish_research":
        return sites_publish(
            params.get("title", "Research"),
            params.get("content", ""),
            params.get("author", "Charlyn AI"),
        )
    elif name == "list_publications":
        return sites_list()
    elif name == "vm_screenshot":
        return vm_screenshot()
    elif name == "vm_mouse_move":
        return vm_mouse_move(params.get("x", 0), params.get("y", 0))
    elif name == "vm_click":
        return vm_click(params.get("x", 0), params.get("y", 0), params.get("button", 1))
    elif name == "vm_type":
        return vm_type(params.get("text", ""))
    elif name == "vm_key":
        return vm_key(params.get("key", ""))
    elif name == "vm_terminal":
        return vm_terminal(params.get("command", ""), params.get("timeout", 30))
    elif name == "vm_find_text":
        return vm_find_text(params.get("text", ""))
    elif name == "vm_click_text":
        return vm_click_text(params.get("text", ""))
    else:
        return f"Unknown tool: {name}"
