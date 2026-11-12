"""Self-contained Python server. No social session cookies are collected or replayed."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

ALLOWED = {
    "linkedin": {"linkedin.com", "www.linkedin.com", "m.linkedin.com"},
    "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
    "instagram": {"instagram.com", "www.instagram.com"},
    "threads": {"threads.net", "www.threads.net", "threads.com", "www.threads.com"},
    "x": {"x.com", "www.x.com", "twitter.com", "www.twitter.com"},
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users(
 id TEXT PRIMARY KEY,workspace TEXT NOT NULL,email TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL,role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(
 token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expiry INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS campaigns(
 id TEXT PRIMARY KEY,workspace TEXT NOT NULL,name TEXT NOT NULL,
 goal INTEGER NOT NULL,target_metric TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assets(
 id TEXT PRIMARY KEY,workspace TEXT NOT NULL,campaign_id TEXT NOT NULL,
 platform TEXT NOT NULL,title TEXT NOT NULL,url TEXT NOT NULL,opens INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS metrics(
 id TEXT PRIMARY KEY,workspace TEXT NOT NULL,asset_id TEXT NOT NULL,
 name TEXT NOT NULL,value INTEGER NOT NULL,source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
 id TEXT PRIMARY KEY,workspace TEXT NOT NULL,actor TEXT NOT NULL,event TEXT NOT NULL);
"""
STATIC = Path(__file__).parent / "static"

def new_id():
    return uuid.uuid4().hex

def password_hash(password):
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("Passwords must have at least 12 characters")
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300000)
    return salt.hex() + ":" + key.hex()

def check_password(password, saved):
    try:
        salt, expected = saved.split(":")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 300000)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (TypeError, ValueError, AttributeError):
        return False

def valid_url(platform, raw):
    if platform not in ALLOWED or not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError("Invalid social platform or URL")
    try:
        p = urlsplit(raw.strip())
        port = p.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if (p.scheme != "https" or p.hostname not in ALLOWED[platform]
        or p.username or p.password or port not in (None, 443)
        or not p.path or p.path == "/" or "\\" in raw
        or any(ord(ch) < 32 for ch in raw)):
        raise ValueError("Use a direct HTTPS content URL on the selected platform")
    return raw.strip()

def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    return db

class ApiError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message

def create_server(path, email, password, host="127.0.0.1", port=8765, secure=True):
    if "@" not in email:
        raise ValueError("Set AMPLIFIER_ADMIN_EMAIL")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        if not db.execute("SELECT id FROM users LIMIT 1").fetchone():
            wid, user_id = new_id(), new_id()
            db.execute("INSERT INTO workspaces VALUES (?,?)", (wid, "Tapas Advisory"))
            db.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                       (user_id, wid, email.lower(), password_hash(password), "superadmin"))
    class Handler(BaseHTTPRequestHandler):
        server_version = "TapasAmplifier/0.1"
        def send_data(self, code, data, cookie=None):
            out = json.dumps(data).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.headers_common()
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(out)

        def headers_common(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; frame-ancestors 'none'")

        def cookie(self, value, clear=False):
            text = f"tapas_session={value}; Path=/; HttpOnly; SameSite=Lax"
            if secure: text += "; Secure"
            text += "; Max-Age=" + ("0" if clear else "43200")
            return text

        def get_session(self, db):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return None
            if "tapas_session" not in cookie:
                return None
            token = cookie["tapas_session"].value
            digest = hashlib.sha256(token.encode()).hexdigest()
            return db.execute("""SELECT users.*, sessions.csrf
                FROM sessions JOIN users ON sessions.user_id=users.id
                WHERE sessions.token_hash=? AND sessions.expiry>?""",
                (digest, int(time.time()))).fetchone()

        def user(self, db, csrf=False, roles=None):
            u = self.get_session(db)
            if u is None: raise ApiError(401, "Sign in required")
            if csrf and not hmac.compare_digest(
                    self.headers.get("X-CSRF-Token", ""), u["csrf"]):
                raise ApiError(403, "Invalid CSRF token")
            if roles and u["role"] not in roles:
                raise ApiError(403, "Insufficient permission")
            return u

        def read_json(self):
            try: length = int(self.headers.get("Content-Length", "0"))
            except ValueError: raise ApiError(400, "Invalid body length")
            if not 0 < length <= 32768:
                raise ApiError(413, "JSON body must be under 32 KB")
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise ApiError(415, "Expected JSON")
            try: body = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError): raise ApiError(400, "Invalid JSON")
            if not isinstance(body, dict):
                raise ApiError(400, "Expected JSON object")
            return body

        def do_GET(self):
            self.dispatch("GET")

        def do_POST(self):
            self.dispatch("POST")

        def dispatch(self, method):
            try:
                route = urlsplit(self.path).path
                if method == "GET" and route in ("/", "/app.js", "/style.css"):
                    file_name = "index.html" if route == "/" else route[1:]
                    content = (STATIC / file_name).read_bytes()
                    mime = {"index.html":"text/html", "app.js":"application/javascript",
                            "style.css":"text/css"}[file_name]
                    self.send_response(200)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(content)))
                    self.headers_common()
                    self.end_headers()
                    self.wfile.write(content)
                    return
                if method == "GET" and route == "/health":
                    return self.send_data(200, {"status":"ok"})
                with connect(path) as db:
                    if method == "POST" and route == "/api/login":
                        b = self.read_json()
                        u = db.execute("SELECT * FROM users WHERE email=?",
                            (str(b.get("email", "")).lower(),)).fetchone()
                        if not u or not check_password(b.get("password", ""), u["password_hash"]):
                            raise ApiError(401, "Incorrect login")
                        token = secrets.token_urlsafe(32)
                        csrf = secrets.token_urlsafe(24)
                        db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                            (hashlib.sha256(token.encode()).hexdigest(),
                             u["id"], csrf, int(time.time())+43200))
                        return self.send_data(200,
                            {"email":u["email"], "role":u["role"], "csrf":csrf},
                            self.cookie(token))
                    if method == "GET" and route.startswith("/out/"):
                        u = self.user(db)
                        rid = route[len("/out/"):]
                        row = db.execute("SELECT * FROM assets WHERE id=? AND workspace=?",
                                         (rid,u["workspace"])).fetchone()
                        if row is None: raise ApiError(404, "Asset not found")
                        url = valid_url(row["platform"],row["url"])
                        db.execute("UPDATE assets SET opens=opens+1 WHERE id=?",(rid,))
                        self.send_response(302)
                        self.send_header("Location",url)
                        self.send_header("Referrer-Policy","no-referrer")
                        self.send_header("Cache-Control","no-store")
                        self.send_header("Content-Length","0")
                        self.end_headers()
                        return
                    if method == "GET":
                        u = self.user(db)
                        ws = u["workspace"]
                        if route == "/api/me":
                            return self.send_data(200,{"email":u["email"],"role":u["role"],"csrf":u["csrf"]})
                        if route == "/api/platforms":
                            return self.send_data(200,{"platforms":list(ALLOWED),
                                "integration_status":"manual_links_only"})
                        if route == "/api/campaigns":
                            rows = db.execute("SELECT * FROM campaigns WHERE workspace=?",(ws,)).fetchall()
                            return self.send_data(200,{"campaigns":[dict(r) for r in rows]})
                        if route == "/api/assets":
                            rows = db.execute("SELECT * FROM assets WHERE workspace=?",(ws,)).fetchall()
                            return self.send_data(200,{"assets":[dict(r) for r in rows]})
                        if route == "/api/stats":
                            count = db.execute("SELECT COUNT(*) FROM campaigns WHERE workspace=?",(ws,)).fetchone()[0]
                            assets = db.execute("SELECT COUNT(*),COALESCE(SUM(opens),0) FROM assets WHERE workspace=?",(ws,)).fetchone()
                            return self.send_data(200,{"campaigns":count,"assets":assets[0],
                               "outbound_opens":assets[1],"verified_platform_metrics":None,
                               "verification_status":"Official APIs not connected"})
                    if method == "POST":
                        u = self.user(db, csrf=True)
                        ws = u["workspace"]
                        b = self.read_json()
                        if route == "/api/logout":
                            jar = SimpleCookie()
                            jar.load(self.headers.get("Cookie",""))
                            if "tapas_session" in jar:
                                digest=hashlib.sha256(jar["tapas_session"].value.encode()).hexdigest()
                                db.execute("DELETE FROM sessions WHERE token_hash=?",(digest,))
                            return self.send_data(200,{"ok":True},self.cookie("",True))
                        if route == "/api/campaigns":
                            self.user(db,roles={"admin","superadmin","manager"})
                            name = str(b.get("name","")).strip()
                            goal = b.get("goal",5000)
                            metric = b.get("target_metric","views")
                            if not 1 <= len(name) <= 120 or type(goal) is not int or not 0 <= goal <= 1000000000:
                                raise ApiError(400,"Invalid campaign")
                            if metric not in {"views","impressions","conversions"}:
                                raise ApiError(400,"Invalid metric")
                            rid = new_id()
                            db.execute("INSERT INTO campaigns VALUES (?,?,?,?,?)",
                                (rid,ws,name,goal,metric))
                            return self.send_data(201,{"id":rid})
                        if route == "/api/assets":
                            self.user(db,roles={"admin","superadmin","manager"})
                            platform = b.get("platform")
                            try: url = valid_url(platform,b.get("url"))
                            except ValueError as ex: raise ApiError(400,str(ex))
                            title=str(b.get("title","")).strip()
                            campaign=b.get("campaign_id")
                            if not 1 <= len(title) <= 160 or not db.execute(
                                "SELECT 1 FROM campaigns WHERE id=? AND workspace=?",
                                (campaign,ws)).fetchone():
                                raise ApiError(400,"Invalid title or campaign")
                            rid = new_id()
                            db.execute("INSERT INTO assets(id,workspace,campaign_id,platform,title,url) VALUES (?,?,?,?,?,?)",
                                (rid,ws,campaign,platform,title,url))
                            return self.send_data(201,{"id":rid})
                        if route == "/api/metrics":
                            self.user(db,roles={"admin","superadmin","manager"})
                            rid=b.get("asset_id")
                            if not db.execute("SELECT 1 FROM assets WHERE id=? AND workspace=?",
                                (rid,ws)).fetchone(): raise ApiError(404,"Asset not found")
                            value=b.get("value")
                            name=b.get("name")
                            if type(value) is not int or value < 0 or value > 1000000000 \
                                or name not in {"views","impressions","likes","shares","comments","conversions"} \
                                or b.get("source","manual")!="manual":
                                raise ApiError(400,"Manual metric required; verified API reporting unavailable")
                            db.execute("INSERT INTO metrics VALUES (?,?,?,?,?,?)",
                                (new_id(),ws,rid,name,value,"manual_unverified"))
                            return self.send_data(201,{"verified":False,"source":"manual_unverified"})
                        if route == "/api/workspaces":
                            self.user(db,roles={"superadmin"})
                            name=str(b.get("name","")).strip()
                            email=str(b.get("admin_email","")).lower().strip()
                            if not name or "@" not in email:
                                raise ApiError(400,"Invalid workspace")
                            pwd=password_hash(b.get("admin_password"))
                            wid,uid=new_id(),new_id()
                            db.execute("INSERT INTO workspaces VALUES (?,?)",(wid,name))
                            db.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                                (uid,wid,email,pwd,"admin"))
                            return self.send_data(201,{"workspace_id":wid})
                raise ApiError(404,"Not found")
            except ApiError as exc:
                self.send_data(exc.code,{"error":exc.message})
            except (ValueError,TypeError,KeyError):
                self.send_data(400,{"error":"Invalid input"})
            except sqlite3.IntegrityError:
                self.send_data(409,{"error":"Record conflict"})
            except Exception:
                self.send_data(500,{"error":"Internal server error"})
    server = ThreadingHTTPServer((host,port),Handler)
    return server

def main():
    email=os.environ.get("AMPLIFIER_ADMIN_EMAIL","")
    password=os.environ.get("AMPLIFIER_ADMIN_PASSWORD","")
    if not email or not password:
        raise SystemExit("Set AMPLIFIER_ADMIN_EMAIL and AMPLIFIER_ADMIN_PASSWORD before running")
    server = create_server(
        os.environ.get("AMPLIFIER_DB","./data/amplifier.sqlite3"),
        email,password,
        os.environ.get("AMPLIFIER_HOST","127.0.0.1"),
        int(os.environ.get("AMPLIFIER_PORT","8765")),
        os.environ.get("AMPLIFIER_SECURE_COOKIES","1")=="1")
    print("Tapas Content Amplifier ready",flush=True)
    server.serve_forever()

if __name__=="__main__":
    main()
