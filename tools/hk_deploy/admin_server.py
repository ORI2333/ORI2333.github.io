from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import html
import http.cookies
import ipaddress
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8765
DB_PATH = Path("/var/lib/ori-blog-admin/admin.sqlite3")
INITIAL_PASSWORD_PATH = Path("/var/lib/ori-blog-admin/initial-password.txt")
ACCESS_LOG_PATH = Path("/var/log/nginx/ori-blog-access.log")
CN_CIDR_PATH = Path("/etc/nginx/geoip/cn.conf")
ADMIN_ASSETS_DIR = Path(__file__).with_name("admin_assets")
SESSION_COOKIE = "ori_blog_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 8
VISIT_RETENTION_SECONDS = 60 * 60 * 24 * 7
PBKDF2_ROUNDS = 260_000
STATIC_EXTENSIONS = {
    ".css",
    ".js",
    ".jpg",
    ".jpeg",
    ".gif",
    ".png",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".json",
    ".xml",
    ".txt",
}
IGNORED_UA_KEYWORDS = {
    "bot",
    "spider",
    "crawler",
    "slurp",
    "curl/",
    "wget/",
    "python-requests",
    "go-http-client",
    "httpclient",
    "headlesschrome",
    "itdog",
    "uptime",
    "monitor",
}


LOG_RE = re.compile(
    r'^(?P<ip>\S+) \S+ \S+ \[(?P<time>[^\]]+)\] '
    r'"(?P<method>\S+) (?P<target>\S+) (?P<proto>[^"]+)" '
    r'(?P<status>\d+) (?P<size>\S+) "(?P<referer>[^"]*)" "(?P<ua>[^"]*)"$'
)


def main() -> int:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"ORI blog admin listening on http://{HOST}:{PORT}")
    server.serve_forever()
    return 0


class Handler(BaseHTTPRequestHandler):
    server_version = "OriBlogAdmin/1.0"

    def log_message(self, fmt: str, *args) -> None:
        return

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self.send_text("ok\n")
            return
        if path == "/api/recommend":
            self.send_json(recommend_for_ip(client_ip(self)))
            return
        if path in {"/admin", "/admin/"}:
            if not self.current_user():
                self.send_html(login_page())
                return
            self.send_html(dashboard_page())
            return
        if path == "/admin/password":
            if not self.require_login():
                return
            self.send_html(password_page())
            return
        if path == "/admin/article":
            if not self.require_login():
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            article = query.get("path", [""])[0]
            self.send_html(article_page(article))
            return
        if path in {"/admin/assets/jsvectormap.min.js", "/admin/assets/jsvectormap.css", "/admin/assets/world.js"}:
            if not self.require_login():
                return
            asset_name = path.rsplit("/", 1)[-1]
            asset_path = ADMIN_ASSETS_DIR / asset_name
            content_type = "text/css; charset=utf-8" if asset_path.suffix == ".css" else "application/javascript; charset=utf-8"
            self.send_file(asset_path, content_type)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        form = self.read_form()
        if path == "/admin/login":
            user = form.get("username", "")
            password = form.get("password", "")
            if verify_user(user, password):
                token = create_session(user)
                self.send_response(HTTPStatus.SEE_OTHER)
                self.send_header("Location", "/admin/")
                self.send_header(
                    "Set-Cookie",
                    f"{SESSION_COOKIE}={token}; Path=/admin/; HttpOnly; Secure; SameSite=Lax; Max-Age={SESSION_TTL_SECONDS}",
                )
                self.end_headers()
            else:
                self.send_html(login_page("账号或密码不正确。"), status=HTTPStatus.UNAUTHORIZED)
            return
        if path == "/admin/logout":
            token = session_token(self)
            if token:
                delete_session(token)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/admin/")
            self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; Path=/admin/; Max-Age=0; HttpOnly; Secure; SameSite=Lax")
            self.end_headers()
            return
        if path == "/admin/password":
            if not self.require_login():
                return
            old = form.get("old_password", "")
            new = form.get("new_password", "")
            confirm = form.get("confirm_password", "")
            if new != confirm:
                self.send_html(password_page("两次输入的新密码不一致。"), status=HTTPStatus.BAD_REQUEST)
                return
            if len(new) < 10:
                self.send_html(password_page("新密码至少 10 位。"), status=HTTPStatus.BAD_REQUEST)
                return
            if not verify_user("admin", old):
                self.send_html(password_page("旧密码不正确。"), status=HTTPStatus.UNAUTHORIZED)
                return
            set_password("admin", new)
            self.send_html(password_page("密码已修改。"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def current_user(self) -> str | None:
        token = session_token(self)
        if not token:
            return None
        return user_for_session(token)

    def require_login(self) -> bool:
        if self.current_user():
            return True
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/admin/")
        self.end_headers()
        return False

    def read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(body)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value: dict) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "private, max-age=3600")
        self.end_headers()
        self.wfile.write(data)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            "create table if not exists users (username text primary key, password_hash text not null, updated_at integer not null)"
        )
        conn.execute(
            "create table if not exists sessions (token_hash text primary key, username text not null, expires_at integer not null)"
        )
        conn.execute(
            "create table if not exists ip_cache (ip text primary key, address text not null, updated_at integer not null, country text not null default '', latitude real, longitude real)"
        )
        columns = {row[1] for row in conn.execute("pragma table_info(ip_cache)")}
        for name, definition in (("country", "text not null default ''"), ("latitude", "real"), ("longitude", "real")):
            if name not in columns:
                conn.execute(f"alter table ip_cache add column {name} {definition}")
        exists = conn.execute("select 1 from users where username = 'admin'").fetchone()
        if not exists:
            password = read_initial_password()
            conn.execute(
                "insert into users (username, password_hash, updated_at) values (?, ?, ?)",
                ("admin", hash_password(password), int(time.time())),
            )


def read_initial_password() -> str:
    if INITIAL_PASSWORD_PATH.exists():
        return INITIAL_PASSWORD_PATH.read_text(encoding="utf-8").strip()
    password = secrets.token_urlsafe(18)
    INITIAL_PASSWORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    INITIAL_PASSWORD_PATH.write_text(password + "\n", encoding="utf-8")
    INITIAL_PASSWORD_PATH.chmod(0o600)
    return password


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${b64(salt)}${b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        rounds = int(rounds_raw)
        salt = b64decode(salt_raw)
        expected = b64decode(digest_raw)
    except Exception:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def set_password(username: str, password: str) -> None:
    with connect() as conn:
        conn.execute(
            "update users set password_hash = ?, updated_at = ? where username = ?",
            (hash_password(password), int(time.time()), username),
        )
        conn.execute("delete from sessions where username = ?", (username,))


def verify_user(username: str, password: str) -> bool:
    with connect() as conn:
        row = conn.execute("select password_hash from users where username = ?", (username,)).fetchone()
    return bool(row and verify_password(password, row["password_hash"]))


def create_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with connect() as conn:
        conn.execute("delete from sessions where expires_at < ?", (int(time.time()),))
        conn.execute(
            "insert into sessions (token_hash, username, expires_at) values (?, ?, ?)",
            (hash_token(token), username, int(time.time()) + SESSION_TTL_SECONDS),
        )
    return token


def user_for_session(token: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "select username from sessions where token_hash = ? and expires_at >= ?",
            (hash_token(token), int(time.time())),
        ).fetchone()
    return row["username"] if row else None


def delete_session(token: str) -> None:
    with connect() as conn:
        conn.execute("delete from sessions where token_hash = ?", (hash_token(token),))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_token(handler: BaseHTTPRequestHandler) -> str | None:
    raw = handler.headers.get("Cookie", "")
    cookie = http.cookies.SimpleCookie(raw)
    item = cookie.get(SESSION_COOKIE)
    return item.value if item else None


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def client_ip(handler: BaseHTTPRequestHandler) -> str:
    forwarded = handler.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real = handler.headers.get("X-Real-IP", "")
    if real:
        return real.strip()
    return handler.client_address[0]


def recommend_for_ip(ip: str) -> dict[str, str]:
    if is_cn_ip(ip):
        return {
            "target": "edge",
            "reason_zh": "检测到当前 IP 更接近中国大陆网络，优先推荐腾讯云 CDN 加速线路。",
            "reason_en": "Your IP appears closer to mainland China, so the Tencent Cloud CDN route is recommended.",
            "ip": ip,
        }
    return {
        "target": "hk",
        "reason_zh": "当前网络更适合优先使用香港服务器线路。",
        "reason_en": "The Hong Kong server route is recommended for your current network.",
        "ip": ip,
    }


def is_cn_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if address.is_private or address.is_loopback:
        return False
    for network in cn_networks():
        if address in network:
            return True
    return False


def cn_networks() -> list[ipaddress._BaseNetwork]:
    if not CN_CIDR_PATH.exists():
        return []
    networks = []
    for line in CN_CIDR_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        cidr = line.split()[0]
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return networks


def parse_access_log(include_address: bool = True) -> list[dict[str, str]]:
    if not ACCESS_LOG_PATH.exists():
        return []
    cutoff = int(time.time()) - VISIT_RETENTION_SECONDS
    rows: list[dict[str, str]] = []
    for line in tail_lines(ACCESS_LOG_PATH, 20000):
        match = LOG_RE.match(line)
        if not match:
            continue
        row = match.groupdict()
        timestamp = parse_log_timestamp(row["time"])
        if timestamp < cutoff:
            continue
        try:
            parsed = urllib.parse.urlparse(row["target"])
        except ValueError:
            continue
        row["path"] = urllib.parse.unquote(parsed.path or "/")
        if should_ignore_visit(row):
            continue
        row["_timestamp"] = str(timestamp)
        row["address"] = address_for_ip(row["ip"]) if include_address else ""
        rows.append(row)
    return rows


def parse_log_timestamp(value: str) -> int:
    try:
        return int(dt.datetime.strptime(value, "%d/%b/%Y:%H:%M:%S %z").timestamp())
    except ValueError:
        return 0


def tail_lines(path: Path, max_lines: int) -> list[str]:
    data = path.read_bytes()[-2_500_000:]
    return data.decode("utf-8", errors="replace").splitlines()[-max_lines:]


def should_ignore_visit(row: dict[str, str]) -> bool:
    if row.get("method") != "GET":
        return True
    try:
        if int(row.get("status", "0")) >= 400:
            return True
    except ValueError:
        return True
    if should_ignore_path(row["path"]):
        return True
    ua = row.get("ua", "").lower()
    return any(keyword in ua for keyword in IGNORED_UA_KEYWORDS)


def should_ignore_path(path: str) -> bool:
    if path.startswith("/admin") or path.startswith("/api/"):
        return True
    if path.startswith(("/wp/", "/wp-", "/livewire/", "/index.php", "/xmlrpc.php")):
        return True
    suffix = Path(path).suffix.lower()
    return suffix in STATIC_EXTENSIONS


def is_article_path(path: str) -> bool:
    return (
        re.match(r"^/(?:blog/)?s/[A-Za-z0-9_-]+/?$", path) is not None
        or re.match(r"^/blog/\d{4}/\d{2}/\d{2}/[^/?#]+/?$", path) is not None
    )


def is_gateway_path(path: str) -> bool:
    return path in {"/", "/index.html"}


def location_for_ip(ip: str) -> dict[str, object]:
    try:
        parsed = ipaddress.ip_address(ip)
        if parsed.is_private or parsed.is_loopback:
            return {"address": "本地/内网", "country": "", "latitude": None, "longitude": None}
    except ValueError:
        return {"address": "未知", "country": "", "latitude": None, "longitude": None}
    now = int(time.time())
    with connect() as conn:
        row = conn.execute(
            "select address, country, latitude, longitude, updated_at from ip_cache where ip = ?", (ip,)
        ).fetchone()
    cache_is_complete = bool(row and row["country"] and row["latitude"] is not None and row["longitude"] is not None)
    if row and cache_is_complete and now - int(row["updated_at"]) < 60 * 60 * 24 * 14:
        return {
            "address": row["address"],
            "country": row["country"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
        }
    location = lookup_ip_location(ip)
    with connect() as conn:
        conn.execute(
            "insert or replace into ip_cache (ip, address, country, latitude, longitude, updated_at) values (?, ?, ?, ?, ?, ?)",
            (ip, location["address"], location["country"], location["latitude"], location["longitude"], now),
        )
    return location


def address_for_ip(ip: str) -> str:
    return str(location_for_ip(ip)["address"])


def lookup_ip_location(ip: str) -> dict[str, object]:
    url = "http://ip-api.com/json/" + urllib.parse.quote(ip) + "?lang=zh-CN&fields=status,country,countryCode,regionName,city,lat,lon,query"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {"address": "未知", "country": "", "latitude": None, "longitude": None}
    if data.get("status") != "success":
        return {"address": "未知", "country": "", "latitude": None, "longitude": None}
    parts = [data.get("country"), data.get("regionName"), data.get("city")]
    return {
        "address": " / ".join(str(part) for part in parts if part) or "未知",
        "country": str(data.get("countryCode") or ""),
        "latitude": data.get("lat"),
        "longitude": data.get("lon"),
    }


def dashboard_page() -> str:
    rows = parse_access_log(include_address=False)
    visitors = summarize_visitors(rows)
    total = len(rows)
    gateway = [row for row in rows if is_gateway_path(row["path"])]
    articles = [row for row in rows if is_article_path(row["path"])]
    article_stats = summarize_articles(articles)
    daily = summarize_daily(rows)
    trend_max = max((int(item["count"]) for item in daily), default=1)
    country_counts: dict[str, int] = {}
    markers: list[dict[str, object]] = []
    for visitor in visitors:
        country = str(visitor.get("country") or "").upper()
        if country:
            country_counts[country] = country_counts.get(country, 0) + int(visitor["count"])
        latitude = visitor.get("latitude")
        longitude = visitor.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            markers.append(
                {
                    "name": f'{visitor["address"]} · {visitor["count"]} 次',
                    "coords": [float(latitude), float(longitude)],
                }
            )
    map_data = {"countries": country_counts, "markers": markers}
    body = f"""
        <section class="dashboard-intro">
          <div>
            <p class="eyebrow">PRIVATE ANALYTICS</p>
            <h1>最近 7 天访问概览</h1>
            <p class="muted">统计窗口：最近 7×24 小时；同一 IP 的访问已合并为一个访客。</p>
          </div>
          <span class="retention-badge">仅保留最近 7 天</span>
        </section>
        <section class="summary">
          <div><strong>{total}</strong><span>页面访问</span></div>
          <div><strong>{len(visitors)}</strong><span>独立 IP</span></div>
          <div><strong>{len(gateway)}</strong><span>入口页访问</span></div>
          <div><strong>{len(articles)}</strong><span>文章访问</span></div>
        </section>
        <section class="dashboard-grid">
          <section class="panel map-panel">
            <div class="section-heading">
              <div><h2>全球访问分布</h2><p class="muted">定位为 IP 数据库的城市级近似位置，不代表精确住址。</p></div>
              <span class="panel-kpi">{len(markers)} 个定位点</span>
            </div>
            <div id="visitor-map" aria-label="全球访问分布地图"></div>
            <p id="map-empty" class="empty" hidden>最近 7 天暂时没有可定位的访客。</p>
            <p class="map-credit">地图组件：<a href="https://github.com/themustafaomar/jsvectormap" target="_blank" rel="noreferrer">jsVectorMap</a>（MIT）。</p>
          </section>
          <section class="panel trend-panel">
            <div class="section-heading"><div><h2>访问趋势</h2><p class="muted">按服务器本地日期统计</p></div></div>
            <div class="trend-list">{''.join(daily_row(item, trend_max) for item in daily)}</div>
          </section>
        </section>
        <section class="panel">
          <div class="section-heading"><div><h2>文章访问量</h2><p class="muted">点击路径查看最近 7 天的合并访客</p></div></div>
          <table>
            <thead><tr><th>文章路径</th><th>访问</th><th>独立 IP</th><th>最近访问</th></tr></thead>
            <tbody>{''.join(article_row(row) for row in article_stats) or '<tr><td colspan="4" class="empty">暂无文章访问</td></tr>'}</tbody>
          </table>
        </section>
        <section class="panel">
          <div class="section-heading"><div><h2>最近访客</h2><p class="muted">同一 IP 仅显示一行，访问次数已汇总</p></div><span class="panel-kpi">{len(visitors)} 个 IP</span></div>
          <table>
            <thead><tr><th>最后访问</th><th>IP</th><th>位置</th><th>访问次数</th><th>最近页面</th></tr></thead>
            <tbody>{''.join(visitor_row(visitor) for visitor in visitors) or '<tr><td colspan="5" class="empty">暂无访客</td></tr>'}</tbody>
          </table>
        </section>
        <script src="/admin/assets/jsvectormap.min.js"></script>
        <script src="/admin/assets/world.js"></script>
        <script>
        (function () {{
          const data = {json_for_script(map_data)};
          const mapNode = document.getElementById('visitor-map');
          const emptyNode = document.getElementById('map-empty');
          if (!mapNode || (data.markers.length === 0 && Object.keys(data.countries).length === 0)) {{
            if (mapNode) mapNode.hidden = true;
            if (emptyNode) emptyNode.hidden = false;
            return;
          }}
          if (typeof window.jsVectorMap !== 'function') {{
            mapNode.hidden = true;
            if (emptyNode) {{ emptyNode.hidden = false; emptyNode.textContent = '地图组件加载失败，仍可查看下方访客列表。'; }}
            return;
          }}
          new window.jsVectorMap({{
            selector: '#visitor-map',
            map: 'world',
            zoomButtons: true,
            zoomOnScroll: false,
            markers: data.markers,
            markerStyle: {{ initial: {{ fill: '#f9736b', stroke: '#ffffff', strokeWidth: 1.5 }} }},
            markerLabelStyle: {{ initial: {{ display: 'none' }} }},
            visualizeData: {{ scale: ['#e5f4f2', '#176b66'], values: data.countries }},
            regionStyle: {{ initial: {{ fill: '#d8e7e8', stroke: '#ffffff', strokeWidth: 0.45 }} }}
          }});
        }})();
        </script>
        """
    head = (
        '<link rel="stylesheet" href="/admin/assets/jsvectormap.css">'
    )
    return layout("访问统计", body, head=head)


def summarize_articles(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for row in rows:
        path = normalize_article_path(row["path"])
        item = stats.setdefault(path, {"path": path, "count": 0, "ips": set(), "last": "", "last_timestamp": -1})
        item["count"] = int(item["count"]) + 1
        item["ips"].add(row["ip"])  # type: ignore[union-attr]
        timestamp = int(row.get("_timestamp", "0"))
        if timestamp >= int(item["last_timestamp"]):
            item["last_timestamp"] = timestamp
            item["last"] = row["time"]
    result = []
    for item in stats.values():
        result.append(
            {
                "path": item["path"],
                "count": item["count"],
                "ip_count": len(item["ips"]),  # type: ignore[arg-type]
                "last": item["last"],
            }
        )
    return sorted(result, key=lambda item: int(item["count"]), reverse=True)


def summarize_visitors(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    stats: dict[str, dict[str, object]] = {}
    for row in rows:
        ip = row["ip"]
        item = stats.setdefault(
            ip,
            {"ip": ip, "count": 0, "last": "", "last_path": "", "last_ua": "", "last_timestamp": -1},
        )
        item["count"] = int(item["count"]) + 1
        timestamp = int(row.get("_timestamp", "0"))
        if timestamp >= int(item["last_timestamp"]):
            item["last_timestamp"] = timestamp
            item["last"] = row["time"]
            item["last_path"] = row["path"]
            item["last_ua"] = row.get("ua", "")
    result: list[dict[str, object]] = []
    for item in stats.values():
        location = location_for_ip(str(item["ip"]))
        result.append({**item, **location})
    return sorted(result, key=lambda item: int(item["last_timestamp"]), reverse=True)


def summarize_daily(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    today = dt.datetime.now().date()
    counts: dict[dt.date, int] = {}
    for row in rows:
        try:
            day = dt.datetime.fromtimestamp(int(row.get("_timestamp", "0"))).date()
        except (TypeError, ValueError, OSError):
            continue
        counts[day] = counts.get(day, 0) + 1
    return [
        {"label": (today - dt.timedelta(days=offset)).strftime("%m-%d"), "count": counts.get(today - dt.timedelta(days=offset), 0)}
        for offset in range(6, -1, -1)
    ]


def normalize_article_path(path: str) -> str:
    return path if path.endswith("/") else path + "/"


def article_page(article: str) -> str:
    rows = [
        row
        for row in parse_access_log(include_address=False)
        if normalize_article_path(row["path"]) == normalize_article_path(article)
    ]
    visitors = summarize_visitors(rows)
    return layout(
        "文章访问详情",
        f"""
        <section class="panel article-detail">
          <div class="section-heading"><div><h1>{escape(article)}</h1><p class="muted">最近 7 天访问 {len(rows)} 次，合并后独立 IP {len(visitors)} 个。</p></div><span class="retention-badge">同一 IP 已合并</span></div>
          <table>
            <thead><tr><th>最后访问</th><th>IP</th><th>位置</th><th>访问次数</th><th>User-Agent（最后一次）</th></tr></thead>
            <tbody>{''.join(article_visit_row(row) for row in visitors) or '<tr><td colspan="5" class="empty">暂无访问</td></tr>'}</tbody>
          </table>
        </section>
        """,
    )


def login_page(message: str = "") -> str:
    alert = f'<p class="alert">{escape(message)}</p>' if message else ""
    return base_page(
        "后台登录",
        f"""
        <main class="login">
          <form method="post" action="/admin/login">
            <h1>博客统计后台</h1>
            {alert}
            <label>账号<input name="username" value="admin" autocomplete="username"></label>
            <label>密码<input name="password" type="password" autocomplete="current-password"></label>
            <button type="submit">登录</button>
          </form>
        </main>
        """,
    )


def password_page(message: str = "") -> str:
    alert = f'<p class="alert ok">{escape(message)}</p>' if message else ""
    return layout(
        "修改密码",
        f"""
        <section class="panel narrow">
          {alert}
          <form method="post" action="/admin/password">
            <label>旧密码<input name="old_password" type="password" autocomplete="current-password"></label>
            <label>新密码<input name="new_password" type="password" autocomplete="new-password"></label>
            <label>确认新密码<input name="confirm_password" type="password" autocomplete="new-password"></label>
            <button type="submit">保存</button>
          </form>
        </section>
        """,
    )


def layout(title: str, body: str, head: str = "") -> str:
    return base_page(
        title,
        f"""
        <header>
          <div><strong>ORI 博客统计后台</strong><span>{escape(title)}</span></div>
          <nav>
            <a href="/admin/">统计</a>
            <a href="/admin/password">修改密码</a>
            <form method="post" action="/admin/logout"><button type="submit">退出</button></form>
          </nav>
        </header>
        <main>{body}</main>
        """,
        head=head,
    )


def base_page(title: str, body: str, head: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - ORI 博客统计后台</title>
  {head}
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Microsoft YaHei UI", "Segoe UI", system-ui, sans-serif; background: #f3f6f8; color: #17212f; }}
    header {{ display: flex; justify-content: space-between; align-items: center; gap: 20px; padding: 18px 28px; background: #15202b; color: #fff; }}
    header span {{ display: block; margin-top: 4px; color: #c8d4df; font-size: 13px; }}
    nav {{ display: flex; align-items: center; gap: 12px; }}
    nav a, button {{ border: 1px solid #c9d4df; border-radius: 6px; padding: 8px 12px; background: #fff; color: #17212f; text-decoration: none; cursor: pointer; font: inherit; }}
    nav form {{ margin: 0; }}
    main {{ padding: 28px 24px 40px; max-width: 1320px; margin: 0 auto; }}
    .dashboard-intro, .section-heading {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }}
    .dashboard-intro {{ margin-bottom: 18px; }}
    .dashboard-intro h1 {{ margin: 0 0 8px; font-size: clamp(24px, 3vw, 34px); }}
    .eyebrow {{ margin: 0 0 8px; color: #176b66; font-size: 11px; font-weight: 800; letter-spacing: .16em; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }}
    .summary div, .panel, .login form {{ background: #fff; border: 1px solid #d8e0ea; border-radius: 12px; box-shadow: 0 12px 28px rgba(20, 31, 48, .08); }}
    .summary div {{ padding: 18px; }}
    .summary strong {{ display: block; font-size: 28px; color: #176b66; }}
    .summary span, .muted {{ color: #647386; }}
    .retention-badge, .panel-kpi {{ display: inline-flex; align-items: center; flex: none; border-radius: 999px; padding: 7px 11px; background: #e8f6f3; color: #176b66; font-size: 12px; font-weight: 700; white-space: nowrap; }}
    .panel {{ padding: 20px; margin-bottom: 18px; overflow-x: auto; }}
    .panel.narrow {{ max-width: 560px; }}
    .dashboard-grid {{ display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(280px, .85fr); gap: 18px; align-items: stretch; }}
    .map-panel, .trend-panel {{ min-width: 0; }}
    #visitor-map {{ height: 420px; min-width: 560px; margin-top: 12px; border-radius: 10px; background: linear-gradient(145deg, #f7fbfb, #edf5f5); }}
    .map-credit {{ margin: 8px 0 0; color: #8491a1; font-size: 11px; }}
    .map-credit a {{ color: #176b66; }}
    .trend-list {{ display: grid; gap: 13px; margin-top: 22px; }}
    .trend-row {{ display: grid; grid-template-columns: 48px 1fr 38px; align-items: center; gap: 10px; font-size: 12px; }}
    .trend-bar {{ height: 9px; overflow: hidden; border-radius: 99px; background: #e8eef1; }}
    .trend-bar i {{ display: block; height: 100%; min-width: 2px; border-radius: inherit; background: linear-gradient(90deg, #48b8a8, #176b66); }}
    .trend-count {{ color: #176b66; font-weight: 800; text-align: right; }}
    h1, h2 {{ margin: 0 0 8px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ padding: 11px 9px; border-bottom: 1px solid #e5ebf2; text-align: left; vertical-align: top; }}
    th {{ color: #516173; font-weight: 700; white-space: nowrap; }}
    td.path, td.ua {{ overflow-wrap: anywhere; }}
    td.path a {{ color: #176b66; font-weight: 600; }}
    .empty {{ padding: 24px 9px; color: #8491a1; text-align: center; }}
    .login {{ min-height: 100vh; display: grid; place-items: center; padding: 20px; }}
    .login form {{ width: min(420px, 100%); padding: 22px; }}
    label {{ display: grid; gap: 7px; margin: 0 0 14px; color: #516173; }}
    input {{ min-height: 38px; padding: 8px 10px; border: 1px solid #d4dde8; border-radius: 6px; font: inherit; }}
    form button[type="submit"], .login button {{ background: #176b66; border-color: #176b66; color: white; font-weight: 700; }}
    .alert {{ padding: 10px 12px; border-radius: 6px; background: #fff5ec; color: #95430d; }}
    .alert.ok {{ background: #eefaf3; color: #176b66; }}
    @media (max-width: 900px) {{ .dashboard-grid {{ grid-template-columns: 1fr; }} }}
    @media (max-width: 760px) {{ header, nav, .dashboard-intro, .section-heading {{ align-items: flex-start; flex-direction: column; }} .summary {{ grid-template-columns: 1fr 1fr; }} main {{ padding: 20px 14px 32px; }} #visitor-map {{ min-width: 0; height: 320px; }} }}
  </style>
</head>
<body>{body}</body>
</html>"""
def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def daily_row(item: dict[str, object], maximum: int) -> str:
    count = int(item["count"])
    width = min(100, max(2, count * 100 // max(1, maximum)))
    return f'<div class="trend-row"><span>{escape(item["label"])}</span><span class="trend-bar"><i style="width:{width}%"></i></span><b class="trend-count">{count}</b></div>'


def visitor_row(row: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(row['last'])}</td>"
        f"<td>{escape(row['ip'])}</td>"
        f"<td>{escape(row['address'])}</td>"
        f"<td><strong>{row['count']}</strong></td>"
        f'<td class="path">{escape(row["last_path"])}</td>'
        "</tr>"
    )


def article_visit_row(row: dict[str, object]) -> str:
    return (
        "<tr>"
        f"<td>{escape(row['last'])}</td>"
        f"<td>{escape(row['ip'])}</td>"
        f"<td>{escape(row['address'])}</td>"
        f"<td><strong>{row['count']}</strong></td>"
        f'<td class="ua">{escape(row["last_ua"])}</td>'
        "</tr>"
    )


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def article_row(row: dict[str, object]) -> str:
    path = str(row["path"])
    link = "/admin/article?path=" + urllib.parse.quote(path, safe="")
    return (
        "<tr>"
        f'<td class="path"><a href="{escape(link)}">{escape(path)}</a></td>'
        f"<td>{row['count']}</td>"
        f"<td>{row['ip_count']}</td>"
        f"<td>{escape(str(row['last']))}</td>"
        "</tr>"
    )


if __name__ == "__main__":
    raise SystemExit(main())


