import os
import re
import random
import string
import sqlite3
import requests
from datetime import datetime
from flask import Flask, request, redirect, render_template, jsonify, abort

app = Flask(__name__)
DATABASE = os.environ.get("DATABASE_PATH", "links.db")

# All Amazon regional store domains
AMAZON_DOMAINS = {
    "US": ("amazon.com",        "🇺🇸 United States"),
    "GB": ("amazon.co.uk",      "🇬🇧 United Kingdom"),
    "CA": ("amazon.ca",         "🇨🇦 Canada"),
    "AU": ("amazon.com.au",     "🇦🇺 Australia"),
    "DE": ("amazon.de",         "🇩🇪 Germany"),
    "FR": ("amazon.fr",         "🇫🇷 France"),
    "IT": ("amazon.it",         "🇮🇹 Italy"),
    "ES": ("amazon.es",         "🇪🇸 Spain"),
    "JP": ("amazon.co.jp",      "🇯🇵 Japan"),
    "IN": ("amazon.in",         "🇮🇳 India"),
    "BR": ("amazon.com.br",     "🇧🇷 Brazil"),
    "MX": ("amazon.com.mx",     "🇲🇽 Mexico"),
    "NL": ("amazon.nl",         "🇳🇱 Netherlands"),
    "SE": ("amazon.se",         "🇸🇪 Sweden"),
    "PL": ("amazon.pl",         "🇵🇱 Poland"),
    "SG": ("amazon.sg",         "🇸🇬 Singapore"),
    "TR": ("amazon.com.tr",     "🇹🇷 Turkey"),
    "AE": ("amazon.ae",         "🇦🇪 UAE"),
    "SA": ("amazon.sa",         "🇸🇦 Saudi Arabia"),
    "EG": ("amazon.eg",         "🇪🇬 Egypt"),
    "BE": ("amazon.com.be",     "🇧🇪 Belgium"),
    "CN": ("amazon.cn",         "🇨🇳 China"),
}

OTHER_STORES = {
    "apple_books":  "Apple Books",
    "google_play":  "Google Play Books",
    "kobo":         "Kobo",
    "barnes_noble": "Barnes & Noble",
    "bookshop":     "Bookshop.org",
    "libro_fm":     "Libro.fm",
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS links (
                id          TEXT PRIMARY KEY,
                asin        TEXT NOT NULL,
                title       TEXT,
                author      TEXT,
                cover_url   TEXT,
                created_at  TEXT,
                total_clicks INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS store_links (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id  TEXT NOT NULL,
                store    TEXT NOT NULL,
                url      TEXT NOT NULL,
                FOREIGN KEY (link_id) REFERENCES links (id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                link_id      TEXT NOT NULL,
                country_code TEXT,
                clicked_at   TEXT,
                FOREIGN KEY (link_id) REFERENCES links (id)
            )
        """)
    conn.close()


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def extract_asin(url: str) -> str | None:
    """Extract a 10-character Amazon ASIN from any Amazon URL format."""
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"amazon\.[^/]+/(?:[^/]+/)*([A-Z0-9]{10})(?:[/?]|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def generate_id(author: str = "", title: str = "") -> str:
    """Generate a unique short ID from author and title."""
    slug_text = f"{author} {title}".lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug_text).strip("-")
    slug = slug[:40]
    
    conn = get_db()
    base_slug = slug
    counter = 1
    
    while True:
        check_id = slug if counter == 1 else f"{base_slug}-{counter}"
        exists = conn.execute("SELECT id FROM links WHERE id = ?", (check_id,)).fetchone()
        if not exists:
            conn.close()
            return check_id
        counter += 1


def get_country_from_ip(ip: str) -> str:
    """Resolve a country code from an IP address using ip-api.com (free)."""
    if not ip or ip in ("127.0.0.1", "::1"):
        return "US"
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}?fields=countryCode",
            timeout=3,
        )
        if resp.ok:
            return resp.json().get("countryCode", "US")
    except Exception:
        pass
    return "US"


def build_amazon_url(asin: str, country_code: str) -> str:
    domain, _ = AMAZON_DOMAINS.get(country_code, AMAZON_DOMAINS["US"])
    return f"https://www.{domain}/dp/{asin}"


def get_real_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", other_stores=OTHER_STORES)


@app.route("/create", methods=["POST"])
def create_link():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body."}), 400

    amazon_url  = data.get("amazon_url", "").strip()
    title       = data.get("title", "").strip() or "Unknown Book"
    author      = data.get("author", "").strip()
    cover_url   = data.get("cover_url", "").strip()
    extra_stores = data.get("extra_stores", {})

    asin = extract_asin(amazon_url)
    if not asin:
        return jsonify({"error": "Could not find an ASIN in that URL. Please paste a valid Amazon book page link."}), 400

    link_id = generate_id(author, title)
    conn = get_db()
    with conn:
        conn.execute(
            "INSERT INTO links (id, asin, title, author, cover_url, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (link_id, asin, title, author, cover_url, datetime.utcnow().isoformat()),
        )
        for store, url in extra_stores.items():
            if url and url.strip():
                conn.execute(
                    "INSERT INTO store_links (link_id, store, url) VALUES (?, ?, ?)",
                    (link_id, store, url.strip()),
                )
    conn.close()

    base = request.host_url.rstrip("/")
    short_link = shorten_url(f"{base}/b/{link_id}")
    return jsonify({
        "link": short_link,  # e.g., "https://tinyurl.com/abc123"
        "stats": f"{base}/stats/{link_id}",
        "id":    link_id,
        "asin":  asin,
    })


@app.route("/b/<link_id>")
def redirect_link(link_id):
    conn = get_db()
    link = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if not link:
        conn.close()
        abort(404)

    store_rows = conn.execute(
        "SELECT store, url FROM store_links WHERE link_id = ?", (link_id,)
    ).fetchall()
    conn.close()

    extra_stores = {row["store"]: row["url"] for row in store_rows}

    ip      = get_real_ip()
    country = get_country_from_ip(ip)
    amazon_url = build_amazon_url(link["asin"], country)

    # Record click
    conn = get_db()
    with conn:
        conn.execute("UPDATE links SET total_clicks = total_clicks + 1 WHERE id = ?", (link_id,))
        conn.execute(
            "INSERT INTO clicks (link_id, country_code, clicked_at) VALUES (?, ?, ?)",
            (link_id, country, datetime.utcnow().isoformat()),
        )
    conn.close()

    # No extra stores → straight redirect to regional Amazon
    if not extra_stores:
        return redirect(amazon_url)

    # Extra stores present → show chooser page
    _, country_name = AMAZON_DOMAINS.get(country, AMAZON_DOMAINS["US"])
    enriched_stores = {
        k: {"name": OTHER_STORES.get(k, k), "url": v}
        for k, v in extra_stores.items()
    }
    return render_template(
        "choose.html",
        title=link["title"],
        author=link["author"],
        cover_url=link["cover_url"],
        amazon_url=amazon_url,
        country_name=country_name,
        extra_stores=enriched_stores,
    )


@app.route("/stats/<link_id>")
def stats(link_id):
    conn = get_db()
    link = conn.execute("SELECT * FROM links WHERE id = ?", (link_id,)).fetchone()
    if not link:
        conn.close()
        abort(404)

    rows = conn.execute(
        """SELECT country_code, COUNT(*) AS count
           FROM clicks WHERE link_id = ?
           GROUP BY country_code ORDER BY count DESC""",
        (link_id,),
    ).fetchall()
    conn.close()

    countries = []
    for row in rows:
        code = row["country_code"] or "??"
        _, name = AMAZON_DOMAINS.get(code, (None, code))
        countries.append({"code": code, "name": name, "count": row["count"]})

    base = request.host_url.rstrip("/")
    return render_template(
        "stats.html",
        link=dict(link),
        countries=countries,
        short_url=f"{base}/b/{link_id}",
    )


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
