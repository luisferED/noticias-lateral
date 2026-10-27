import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from xml.etree import ElementTree

import server


ITEM = {
    "title": "Un titular de prueba suficientemente largo para aparecer en portada",
    "url": "https://eldeber.com.bo/pais/prueba",
    "image": "https://pxcdn.eldeber.com.bo/prueba.jpg",
    "section": "PAIS",
}


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.data = Path(self.directory.name)
        for name, value in (("DATA_DIR", self.data), ("_cache_file", self.data / "headlines.json"),
                            ("_cache", {"expires_at": 0, "payload": None})):
            patcher = patch.object(server, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = server.app.test_client()

    def test_public_routes_and_private_files(self):
        for path in ("/", "/index.html", "/healthz", "/api/config",
                     "/assets/fonts/FlamaCondensed-Black.ttf"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                response.close()
        for path in ("/server.py", "/.env", "/server-8095.log", "/data/headlines.json",
                     "/.git/config", "/assets/../server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_shared_configuration(self):
        config = self.client.get("/api/config").json
        self.assertEqual(config["rotate_seconds"], server.ROTATE_SECONDS)
        self.assertEqual(config["max_items"], server.MAX_ITEMS)
        self.assertEqual((config["width"], config["height"]), (1920, 1080))

    def test_qr_is_svg_with_white_background_and_local_generation(self):
        with patch.object(server, "fetch_homepage") as fetch:
            response = self.client.get("/api/qr.svg", query_string={"url": ITEM["url"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/svg+xml")
        image = ElementTree.fromstring(response.data)
        self.assertEqual(image.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertEqual(image.attrib["shape-rendering"], "crispEdges")
        self.assertIsNotNone(image.find("{http://www.w3.org/2000/svg}path"))
        self.assertIn(b'fill="white"', response.data)
        self.assertIn("max-age=86400", response.headers["Cache-Control"])
        fetch.assert_not_called()

    def test_qr_changes_with_article_url(self):
        first = self.client.get("/api/qr.svg", query_string={"url": ITEM["url"]})
        second = self.client.get("/api/qr.svg", query_string={"url": ITEM["url"] + "-otra"})
        self.assertNotEqual(first.data, second.data)

    def test_qr_rejects_non_article_and_external_urls(self):
        for url in ("", "https://example.com/pais/nota", "javascript:alert(1)",
                    "https://eldeber.com.bo/", "https://eldeber.com.bo/pais",
                    "https://eldeber.com.bo.example.org/pais/nota", "https://[invalid",
                    "https://eldeber.com.bo/pais/" + "x" * 2048):
            with self.subTest(url=url[:60]):
                response = self.client.get("/api/qr.svg", query_string={"url": url})
                self.assertEqual(response.status_code, 400)

    def test_cache_persisted_and_concurrent_requests_deduplicated(self):
        with patch.object(server, "fetch_homepage", return_value="html") as fetch, \
                patch.object(server, "extract_headlines", return_value=[ITEM]):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _: server.get_payload(), range(8)))
        self.assertTrue(all(result["ok"] for result in results))
        self.assertEqual(fetch.call_count, 1)
        saved = json.loads((self.data / "headlines.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["items"], [ITEM])

    def test_cold_start_recovers_saved_queue_when_offline(self):
        saved = {"ok": True, "updated_at": 1, "items": [ITEM]}
        (self.data / "headlines.json").write_text(json.dumps(saved), encoding="utf-8")
        with patch.object(server, "fetch_homepage", side_effect=URLError("offline")):
            response = self.client.get("/api/headlines")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["stale"])
        self.assertFalse(response.json["ok"])
        self.assertEqual(response.json["items"], [ITEM])

    def test_no_queue_and_no_source_returns_503(self):
        with patch.object(server, "fetch_homepage", side_effect=URLError("offline")):
            response = self.client.get("/api/headlines")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json["items"], [])

    def test_legacy_or_malformed_cache_is_ignored_without_crash(self):
        for saved in ([ITEM], {"items": [ITEM]},
                      {"updated_at": 1, "items": [{"title": "Antigua", "url": ITEM["url"]}]},
                      {"updated_at": 1, "items": [dict(ITEM, url="javascript:alert(1)")]}):
            with self.subTest(saved=saved):
                server._cache.update(expires_at=0, payload=None)
                (self.data / "headlines.json").write_text(json.dumps(saved), encoding="utf-8")
                with patch.object(server, "fetch_homepage", side_effect=URLError("offline")):
                    response = self.client.get("/api/headlines")
                self.assertEqual(response.status_code, 503)

    def test_all_extracted_article_urls_are_accepted_by_qr_endpoint(self):
        html = (f'<a href="/pais/nota-publica"><img src="{ITEM["image"]}">'
                f'{ITEM["title"]}</a>')
        items = server.extract_headlines(html)
        self.assertEqual(len(items), 1)
        for item in items:
            self.assertEqual(self.client.get("/api/qr.svg", query_string={"url": item["url"]}).status_code, 200)
        self.assertFalse(server.is_article_url("https://eldeber.com.bo/pais//"))

    def test_source_parser_deduplicates_and_limits_items(self):
        html = "".join(
            f'<a href="/pais/noticia-{i}"><img src="https://pxcdn.eldeber.com.bo/{i}.jpg">'
            f'Este titular de prueba supera el largo minimo de portada numero {i}</a>'
            for i in range(20)
        )
        with patch.object(server, "MAX_ITEMS", 14):
            items = server.extract_headlines(html + html)
        self.assertEqual(len(items), 14)
        self.assertEqual(len({item["url"] for item in items}), 14)

    def test_image_hostname_must_belong_to_source(self):
        self.assertTrue(server.is_valid_image(ITEM["image"]))
        self.assertFalse(server.is_valid_image("https://eldeber.com.bo.example.org/a.jpg"))


if __name__ == "__main__":
    unittest.main()
