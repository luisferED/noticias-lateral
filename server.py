from __future__ import annotations

import json
from functools import lru_cache
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from flask import Flask, Response, jsonify, request, send_from_directory
import qrcode
from qrcode.exceptions import DataOverflowError
from qrcode.image.svg import SvgPathFillImage

from config import BASE_DIR, DATA_DIR, HOST, MAX_ITEMS, PORT, REFRESH_SECONDS, ROTATE_SECONDS

SOURCE_URL = "https://eldeber.com.bo/"
CACHE_SECONDS = REFRESH_SECONDS
logger = logging.getLogger(__name__)
_cache_lock = threading.Lock()
_cache_file = DATA_DIR / "headlines.json"

_cache = {
    "expires_at": 0.0,
    "payload": None,
}


@dataclass
class Anchor:
    href: str
    text: str = ""
    images: list[str] = field(default_factory=list)


class ElDeberParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[Anchor] = []
        self.current: Anchor | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = {name.lower(): value or "" for name, value in attrs}

        if tag == "a":
            href = attrs_map.get("href", "").strip()
            self.current = Anchor(href=normalize_url(href))
            return

        if self.current and tag in {"img", "amp-img", "source"}:
            image = attrs_map.get("src") or attrs_map.get("data-src")
            if not image:
                image = first_srcset_url(attrs_map.get("srcset", ""))
            if image:
                self.current.images.append(normalize_image_url(image))

    def handle_data(self, data: str) -> None:
        if self.current:
            self.current.text += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current:
            self.current.text = clean_text(self.current.text)
            self.current.images = [
                image for image in dict.fromkeys(self.current.images)
                if is_valid_image(image)
            ]
            self.anchors.append(self.current)
            self.current = None


def first_srcset_url(srcset: str) -> str:
    if not srcset:
        return ""
    return srcset.split(",")[0].strip().split(" ")[0]


def normalize_url(url: str) -> str:
    url = unescape(url or "").strip()
    if not url:
        return ""
    return urljoin(SOURCE_URL, url)


def normalize_image_url(url: str) -> str:
    url = unescape(url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    if "pxcdn.eldeber.com.bo" in url:
        url = re.sub(r"([?&]cw=)\d+", r"\g<1>850", url)
        url = re.sub(r"([?&]ch=)\d+", r"\g<1>478", url)
    return url


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def is_valid_image(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return parsed.scheme in {"http", "https"} and (
        hostname == "eldeber.com.bo" or hostname.endswith(".eldeber.com.bo")
    )


def is_valid_headline(text: str, url: str) -> bool:
    if len(text) < 36 or len(text) > 210:
        return False
    if "{{" in text or "}}" in text:
        return False
    if not is_article_url(url):
        return False

    blocked = {
        "iniciar sesion",
        "cerrar sesion",
        "radio fm",
        "ver mas noticias",
        "te puede interesar",
        "clasificados",
    }
    lowered = text.lower()
    if any(value in lowered for value in blocked):
        return False
    if text.isupper() and len(text.split()) <= 5:
        return False
    return True


def is_article_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return (len(url) <= 2048 and parsed.scheme == "https" and
                parsed.netloc in {"eldeber.com.bo", "www.eldeber.com.bo"} and
                len([part for part in parsed.path.split("/") if part]) >= 2)
    except ValueError:
        return False


def valid_saved_payload(saved) -> bool:
    # Older caches may contain text-only stories or a different schema.
    return (isinstance(saved, dict) and
            isinstance(saved.get("updated_at"), (int, float)) and
            isinstance(saved.get("items"), list) and bool(saved["items"]) and
            all(isinstance(item, dict) and
                isinstance(item.get("title"), str) and
                isinstance(item.get("url"), str) and is_article_url(item["url"]) and
                isinstance(item.get("image"), str) and is_valid_image(item["image"])
                for item in saved["items"]))


def fetch_homepage() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8", errors="replace")


def extract_headlines(html: str) -> list[dict[str, str]]:
    parser = ElDeberParser()
    parser.feed(html)

    image_by_url: dict[str, str] = {}
    for anchor in parser.anchors:
        if anchor.href and anchor.images:
            image_by_url.setdefault(anchor.href, anchor.images[0])

    seen_titles: set[str] = set()
    seen_urls: set[str] = set()
    items: list[dict[str, str]] = []

    for anchor in parser.anchors:
        title = anchor.text
        url = anchor.href
        if not is_valid_headline(title, url):
            continue
        if title in seen_titles or url in seen_urls:
            continue

        image = image_by_url.get(url)
        if not image and anchor.images:
            image = anchor.images[0]
        if not image:
            continue

        section = infer_section(url)
        items.append({
            "title": title,
            "url": url,
            "image": image,
            "section": section,
        })
        seen_titles.add(title)
        seen_urls.add(url)

        if len(items) >= MAX_ITEMS:
            break

    return items


def infer_section(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "PORTADA"
    first = path.split("/")[0].replace("-", " ")
    return first.upper()[:24]


def get_payload(force: bool = False) -> dict:
    # One upstream request at a time, shared by all browser consumers.
    with _cache_lock:
        return _get_payload_locked(force)


def _get_payload_locked(force: bool = False) -> dict:
    now = time.time()
    if _cache["payload"] is None:
        try:
            saved = json.loads(_cache_file.read_text(encoding="utf-8"))
            if valid_saved_payload(saved):
                saved["items"] = saved["items"][:MAX_ITEMS]
                _cache["payload"] = saved
        except (OSError, ValueError, AttributeError):
            pass
    if not force and _cache["payload"] and now < _cache["expires_at"]:
        return _cache["payload"]
    if force and _cache["payload"] and now - _cache["payload"]["updated_at"] < 30:
        return _cache["payload"]

    try:
        html = fetch_homepage()
        items = extract_headlines(html)
        if not items:
            raise RuntimeError("No se encontraron titulares con foto")
        payload = {
            "ok": True,
            "source": SOURCE_URL,
            "updated_at": int(now),
            "items": items,
        }
        _cache["payload"] = payload
        _cache["expires_at"] = now + CACHE_SECONDS
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            temporary = _cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            temporary.replace(_cache_file)
        except OSError:
            logger.warning("No se pudo guardar la ultima cola", exc_info=True)
        return payload
    except (URLError, OSError, RuntimeError) as error:
        if _cache["payload"]:
            stale = dict(_cache["payload"])
            stale["ok"] = False
            stale["error"] = str(error)
            stale["stale"] = True
            _cache["payload"] = stale
            _cache["expires_at"] = now + 30
            return stale
        return {
            "ok": False,
            "source": SOURCE_URL,
            "updated_at": int(now),
            "error": str(error),
            "items": [],
        }


app = Flask(__name__, static_folder=None)


@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.path == "/api/qr.svg" and response.status_code == 200:
        response.headers["Cache-Control"] = "public, max-age=86400"
    elif not request.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
@app.get("/index.html")
def screen():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/assets/<path:filename>")
def assets(filename):
    return send_from_directory(BASE_DIR / "assets", filename)


@app.get("/healthz")
def health():
    payload = _cache["payload"] or {}
    return jsonify(status="ok", items=len(payload.get("items", [])),
                   source_ok=payload.get("ok"), updated_at=payload.get("updated_at"))


@app.get("/api/config")
def public_config():
    return jsonify(rotate_seconds=ROTATE_SECONDS, refresh_seconds=REFRESH_SECONDS,
                   max_items=MAX_ITEMS, width=1920, height=1080)


@app.get("/api/headlines")
def headlines():
    payload = get_payload()
    return jsonify(payload), 200 if payload.get("items") else 503


@lru_cache(maxsize=128)
def qr_svg(url: str) -> bytes:
    code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,
                         box_size=4, border=4)
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathFillImage)
    image.get_image().set("shape-rendering", "crispEdges")
    return image.to_string()


@app.get("/api/qr.svg")
def article_qr():
    url = request.args.get("url", "").strip()
    if not is_article_url(url):
        return jsonify(error="Se requiere una URL de noticia de El Deber"), 400
    try:
        return Response(qr_svg(url), mimetype="image/svg+xml")
    except DataOverflowError:
        return jsonify(error="La URL es demasiado larga para un QR"), 400


def main() -> None:
    from waitress import serve

    logging.basicConfig(level=logging.INFO)
    print(f"Pantalla local: http://127.0.0.1:{PORT}")
    print(f"Pantalla en red: http://<IP-DE-ESTA-PC>:{PORT}")
    print("Fuente: https://eldeber.com.bo/")
    serve(app, host=HOST, port=PORT, threads=8, channel_timeout=60)


if __name__ == "__main__":
    main()
