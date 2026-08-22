"""Research site publisher — create, serve, and auto-expire web pages."""
import json
import os
import re
import sqlite3
import string
import threading
import time
import random
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
DB_PATH = os.path.join(os.path.dirname(__file__), "sites.db")
SITES_PORT = int(os.getenv("SITES_PORT", "8765"))
SITES_TTL_DAYS = int(os.getenv("SITES_TTL_DAYS", "7"))
SITES_DOMAIN = os.getenv("SITES_DOMAIN", f"http://localhost:{SITES_PORT}")
CLEANUP_INTERVAL = int(os.getenv("SITES_CLEANUP_INTERVAL", "900"))  # 15 min

# Cloudflare Worker (primary hosting — no tunnel needed)
SITES_WORKER_URL = os.getenv("SITES_WORKER_URL", "https://charlyn.dspl.me")
SITES_WORKER_API_KEY = os.getenv("SITES_WORKER_API_KEY", "")

os.makedirs(SITES_DIR, exist_ok=True)

_db_lock = threading.Lock()
_cleanup_thread = None
_cleanup_stop = threading.Event()
_server = None
_server_thread = None

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }} — Charlyn Research</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #000000;
  --text: #ffffff;
  --text-dim: #888888;
  --border: #333333;
  --gold: #c9a84c;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
}
.container { max-width: 720px; margin: 0 auto; padding: 0 24px; }
header {
  padding: 48px 0 32px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 40px;
}
header h1 {
  font-size: 2rem;
  font-weight: 700;
  margin-bottom: 12px;
}
.meta {
  color: var(--text-dim);
  font-size: 0.9rem;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.expiry-badge {
  display: inline-block;
  color: var(--gold);
  font-size: 0.8rem;
  font-weight: 500;
}
main { padding-bottom: 64px; }
.content h1, .content h2, .content h3, .content h4 {
  margin-top: 32px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.4;
}
.content h1 { font-size: 1.75rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
.content h2 { font-size: 1.4rem; }
.content h3 { font-size: 1.15rem; }
.content h4 { font-size: 1rem; color: var(--text-dim); }
.content p { margin-bottom: 16px; }
.content a { color: var(--gold); text-decoration: none; }
.content a:hover { text-decoration: underline; }
.content ul, .content ol { margin: 0 0 16px 24px; }
.content li { margin-bottom: 6px; }
.content code {
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
  font-size: 0.85em;
  background: #111111;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid var(--border);
}
.content pre {
  background: #111111;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 20px;
  margin: 0 0 20px 0;
  overflow-x: auto;
}
.content pre code {
  background: none;
  border: none;
  padding: 0;
  font-size: 0.85rem;
  line-height: 1.6;
  color: var(--text);
}
.content blockquote {
  border-left: 3px solid var(--gold);
  padding: 8px 16px;
  margin: 0 0 16px 0;
  color: var(--text-dim);
}
.content table {
  width: 100%;
  border-collapse: collapse;
  margin: 0 0 20px 0;
  font-size: 0.9rem;
}
.content th, .content td {
  border: 1px solid var(--border);
  padding: 10px 14px;
  text-align: left;
}
.content th {
  background: #111111;
  font-weight: 600;
}
.content hr {
  border: none;
  height: 1px;
  background: var(--border);
  margin: 32px 0;
}
.content img {
  max-width: 100%;
  border-radius: 6px;
  border: 1px solid var(--border);
}
footer {
  border-top: 1px solid var(--border);
  padding: 24px 0;
  text-align: center;
  color: var(--text-dim);
  font-size: 0.85rem;
}
footer a { color: var(--gold); text-decoration: none; }
</style>
</head>
<body>
<div class="container">
<header>
  <h1>{{ title }}</h1>
  <div class="meta">
    <span>By {{ author }}</span>
    <span>{{ created_at }}</span>
    <span class="expiry-badge">Expires {{ expires_at }}</span>
  </div>
</header>
<main class="content">
{{ content_html }}
</main>
<footer>
  Published by <a href="https://github.com/dsplayed">Charlyn AI</a> &mdash; this page auto-expires {{ expires_at }}
</footer>
</div>
</body>
</html>"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Published Research — Charlyn</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #000000;
  --text: #ffffff;
  --text-dim: #888888;
  --border: #333333;
  --gold: #c9a84c;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
}
.container { max-width: 680px; margin: 0 auto; padding: 0 24px; }
header { padding: 64px 0 40px; text-align: center; }
header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 8px; }
header p { color: var(--text-dim); font-size: 1.1rem; }
.sites { list-style: none; padding: 0; }
.site-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 20px 24px;
  margin-bottom: 16px;
  transition: border-color 0.2s;
}
.site-card:hover { border-color: var(--gold); }
.site-card a { text-decoration: none; color: var(--text); display: block; }
.site-card h2 { font-size: 1.2rem; font-weight: 600; margin-bottom: 6px; color: var(--gold); }
.site-card .meta { font-size: 0.85rem; color: var(--text-dim); display: flex; gap: 16px; flex-wrap: wrap; }
.empty { text-align: center; padding: 80px 0; color: var(--text-dim); }
footer {
  text-align: center; padding: 48px 0; color: var(--text-dim); font-size: 0.85rem;
}
footer a { color: var(--gold); text-decoration: none; }
</style>
</head>
<body>
<div class="container">
<header>
  <h1>Published Research</h1>
  <p>Auto-generated by Charlyn AI &mdash; pages expire after {{ ttl_days }} days</p>
</header>
{% if sites %}
<ul class="sites">
{% for s in sites %}
<li class="site-card">
  <a href="{{ s.slug }}/">
    <h2>{{ s.title }}</h2>
    <div class="meta">
      <span>{{ s.author }}</span>
      <span>{{ s.created_at }}</span>
      <span>Expires {{ s.expires_at }}</span>
    </div>
  </a>
</li>
{% endfor %}
</ul>
{% else %}
<div class="empty">
  <p>No published research yet.</p>
</div>
{% endif %}
<footer>
  Powered by <a href="https://github.com/dsplayed/charlyn">Charlyn</a>
</footer>
</div>
</body>
</html>"""


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        slug = "research"
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{slug}-{suffix}"


def _md_to_html(text: str) -> str:
    try:
        import markdown
        return markdown.markdown(text, extensions=["fenced_code", "tables", "codehilite"])
    except ImportError:
        pass
    lines = []
    for line in text.split("\n"):
        if line.startswith("### "):
            lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("```"):
            lines.append("</pre>" if lines and lines[-1].startswith("<pre>") else "<pre><code>")
        elif line.startswith("- ") or line.startswith("* "):
            if not lines or not lines[-1].startswith("<ul>"):
                lines.append("<ul>")
            lines.append(f"<li>{line[2:]}</li>")
        else:
            if lines and lines[-1].startswith("<li>"):
                lines.append("</ul>")
            if line.strip():
                lines.append(f"<p>{line}</p>")
            else:
                lines.append("<br>")
    return "\n".join(lines)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _expires_at() -> str:
    return (datetime.now() + timedelta(days=SITES_TTL_DAYS)).strftime("%Y-%m-%d %H:%M:%S")


class SiteManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    author TEXT DEFAULT 'Charlyn AI',
                    content_raw TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    views INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    def publish(self, title: str, content: str, author: str = "Charlyn AI") -> dict:
        slug = _slugify(title)
        created = _now()
        expires = _expires_at()
        content_html = _md_to_html(content)

        try:
            import jinja2
            tmpl = jinja2.Template(TEMPLATE)
            html = tmpl.render(
                title=title,
                author=author,
                created_at=created,
                expires_at=expires,
                content_html=content_html,
            )
        except ImportError:
            html = f"<html><body><h1>{title}</h1><p>by {author}</p><div>{content_html}</div></body></html>"

        site_dir = os.path.join(SITES_DIR, slug)
        os.makedirs(site_dir, exist_ok=True)
        with open(os.path.join(site_dir, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)

        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sites (slug, title, author, content_raw, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
                (slug, title, author, content, created, expires),
            )
            conn.commit()

        url = f"{SITES_DOMAIN}/{slug}/"
        return {
            "slug": slug,
            "url": url,
            "title": title,
            "created_at": created,
            "expires_at": expires,
        }

    def list_active(self) -> list[dict]:
        now = _now()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT slug, title, author, created_at, expires_at, views FROM sites WHERE expires_at > ? ORDER BY created_at DESC",
                (now,),
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_site(self, slug: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM sites WHERE slug = ?", (slug,))
            conn.commit()
        deleted_local = cur.rowcount > 0
        if deleted_local:
            site_dir = os.path.join(SITES_DIR, slug)
            index_html = os.path.join(site_dir, "index.html")
            if os.path.exists(index_html):
                os.remove(index_html)
            try:
                os.rmdir(site_dir)
            except OSError:
                pass

        # Also delete from Cloudflare Worker
        delete_from_worker(slug)

        return deleted_local

    def cleanup_expired(self) -> int:
        now = _now()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT slug FROM sites WHERE expires_at <= ?", (now,)
            ).fetchall()
            conn.execute("DELETE FROM sites WHERE expires_at <= ?", (now,))
            conn.commit()
        count = 0
        for r in rows:
            slug = r["slug"]
            site_dir = os.path.join(SITES_DIR, slug)
            index_html = os.path.join(site_dir, "index.html")
            if os.path.exists(index_html):
                os.remove(index_html)
            try:
                os.rmdir(site_dir)
            except OSError:
                pass
            count += 1
        return count


_manager = None


def get_manager() -> SiteManager:
    global _manager
    if _manager is None:
        _manager = SiteManager()
    return _manager


# ── HTTP Server ──────────────────────────────────

class SitesHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=SITES_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self._serve_index()
        else:
            super().do_GET()

    def _serve_index(self):
        mgr = get_manager()
        sites = mgr.list_active()
        try:
            import jinja2
            tmpl = jinja2.Template(INDEX_TEMPLATE)
            html = tmpl.render(sites=sites, ttl_days=SITES_TTL_DAYS)
        except ImportError:
            links = "\n".join(
                f'<li><a href="{s["slug"]}/">{s["title"]}</a> — expires {s["expires_at"]}</li>'
                for s in sites
            )
            html = f"<html><body><h1>Published Research</h1><ul>{links}</ul></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html.encode())))
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass


def start_server(port: int = SITES_PORT) -> HTTPServer:
    global _server
    _server = HTTPServer(("0.0.0.0", port), SitesHandler)
    return _server


def start_server_thread(port: int = SITES_PORT) -> threading.Thread:
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return _server_thread
    _server = start_server(port)
    t = threading.Thread(target=_server.serve_forever, daemon=True, name="sites-http")
    t.start()
    _server_thread = t
    return t


def stop_server():
    global _server, _server_thread
    if _server:
        _server.shutdown()
        _server.server_close()
        _server = None
    _server_thread = None


# ── Cleanup Background Task ──────────────────────

def start_cleanup_thread():
    global _cleanup_thread
    if _cleanup_thread and _cleanup_thread.is_alive():
        return _cleanup_thread
    _cleanup_stop.clear()

    def _loop():
        while not _cleanup_stop.is_set():
            try:
                mgr = get_manager()
                count = mgr.cleanup_expired()
                if count:
                    print(f"[Sites] Cleaned up {count} expired site(s)")
            except Exception as e:
                print(f"[Sites] Cleanup error: {e}")
            _cleanup_stop.wait(CLEANUP_INTERVAL)

    _cleanup_thread = threading.Thread(target=_loop, daemon=True, name="sites-cleanup")
    _cleanup_thread.start()
    return _cleanup_thread


def stop_cleanup():
    _cleanup_stop.set()


# ── Convenience ──────────────────────────────────

# ── Cloudflare Worker Publishing ────────────────────

def _worker_api_key() -> str:
    return os.environ.get("SITES_WORKER_API_KEY", SITES_WORKER_API_KEY) or ""


_worker_last_error: str | None = None


def _worker_api_post(path: str, data: dict) -> dict | None:
    """POST to the Worker API using urllib (no external deps needed)."""
    import urllib.request, json, urllib.error
    global _worker_last_error
    api_key = _worker_api_key()
    if not api_key:
        _worker_last_error = "SITES_WORKER_API_KEY not set"
        return None
    try:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{SITES_WORKER_URL}{path}",
            data=body,
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "User-Agent": "Charlyn/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            _worker_last_error = None
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        reason = e.read().decode(errors="replace") if e.fp else str(e)
        _worker_last_error = f"HTTP {e.code}: {reason}"
        print(f"[Sites] Worker API error ({path}): HTTP {e.code} {reason}")
        return None
    except Exception as e:
        _worker_last_error = str(e)
        print(f"[Sites] Worker API error ({path}): {e}")
        return None


def publish_to_worker(title: str, content: str, author: str = "Charlyn AI") -> dict | None:
    """Publish a site via the Cloudflare Worker API (D1). Returns the result dict or None on failure."""
    return _worker_api_post("/api/publish", {"title": title, "content": content, "author": author})


def delete_from_worker(slug: str) -> bool:
    """Delete a site from the Cloudflare Worker. Returns True if successful."""
    result = _worker_api_post("/api/delete", {"slug": slug})
    return result is not None and result.get("deleted") is True


def publish(title: str, content: str, author: str = "Charlyn AI") -> str:
    if not content or not content.strip():
        return "Error: content is empty — provide actual research content to publish."

    mgr = get_manager()
    result = mgr.publish(title, content, author)

    # Also publish to Cloudflare Worker (primary hosting)
    worker_result = publish_to_worker(title, content, author)
    if worker_result:
        url = worker_result["url"]
        status = "OK"
    else:
        url = result["url"]
        status = _worker_last_error or "unknown error"

    return (
        f"Published: {result['title']}\n"
        f"URL: {url}\n"
        f"Created: {result['created_at']}\n"
        f"Expires: {result['expires_at']}\n"
        f"Page will be automatically removed after {SITES_TTL_DAYS} days."
        + (f"\nCloudflare Worker: {status}")
    )


def list_publications() -> str:
    mgr = get_manager()
    sites = mgr.list_active()
    if not sites:
        return "No published research sites."
    lines = [f"Published Research ({len(sites)}):"]
    for s in sites:
        url = f"{SITES_WORKER_URL}/{s['slug']}/"
        lines.append(f"  - {s['title']}")
        lines.append(f"    URL: {url}")
        lines.append(f"    By {s['author']} · Expires {s['expires_at']}")
    return "\n".join(lines)


# ── Migration ──────────────────────────────────────

def migrate_local_to_cloudflare():
    """Push all locally-published sites to the Cloudflare Worker."""
    api_key = _worker_api_key()
    if not api_key:
        print("[Sites] Cannot migrate: SITES_WORKER_API_KEY not set in .env")
        return

    mgr = get_manager()
    mgr._init_db()
    with mgr._get_conn() as conn:
        rows = conn.execute(
            "SELECT slug, title, author, content_raw, created_at, expires_at FROM sites WHERE expires_at > ? ORDER BY created_at DESC",
            (_now(),),
        ).fetchall()
    sites = [dict(r) for r in rows]
    if not sites:
        print("[Sites] No local sites to migrate.")
        return

    print(f"[Sites] Migrating {len(sites)} site(s) to Cloudflare Worker...")
    ok = 0
    fail = 0
    for s in sites:
        print(f"  [{s['slug']}] {s['title']}... ", end="", flush=True)
        result = publish_to_worker(s["title"], s["content_raw"], s["author"])
        if result:
            print(f"OK → {result['url']}")
            ok += 1
        else:
            print("FAILED")
            fail += 1
    print(f"[Sites] Done: {ok} migrated, {fail} failed")


# ── Standalone server runner ─────────────────────

def main():
    import sys
    if "--migrate" in sys.argv:
        migrate_local_to_cloudflare()
        return
    if "--publish" in sys.argv:
        idx = sys.argv.index("--publish")
        if idx + 3 < len(sys.argv):
            title = sys.argv[idx + 1]
            content = sys.argv[idx + 2]
            author = sys.argv[idx + 3] if idx + 3 < len(sys.argv) else "Charlyn AI"
            result = publish(title, content, author)
            print(result)
        else:
            print("Usage: python sites.py --publish <title> <content> [author]")
        return

    print(f"[Sites] Starting HTTP server on port {SITES_PORT}...")
    print(f"[Sites] Sites directory: {SITES_DIR}")
    print(f"[Sites] TTL: {SITES_TTL_DAYS} days, cleanup every {CLEANUP_INTERVAL}s")
    print(f"[Sites] Worker: {SITES_WORKER_URL} ({'configured' if SITES_WORKER_API_KEY else 'no API key - local only'})")
    print(f"[Sites] Tip: run 'python sites.py --migrate' to push local sites to Worker")
    start_cleanup_thread()
    server = start_server()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Sites] Shutting down...")
        stop_cleanup()
        server.shutdown()


if __name__ == "__main__":
    main()
