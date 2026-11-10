"""Panel web sunucusu: giriş, roller, Odoo başına kapsam, CSRF, ajana iletim, webhook ve zip geçişi."""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from panel import panel as P


class SahteAjan(BaseHTTPRequestHandler):
    istekler = []

    def _isle(self, yontem):
        uzunluk = int(self.headers.get("Content-Length") or 0)
        govde = self.rfile.read(uzunluk) if uzunluk else b""
        SahteAjan.istekler.append({"yontem": yontem, "yol": self.path, "govde": govde,
                                   "basliklar": dict(self.headers.items())})
        if self.headers.get("X-Ajan-Anahtar") != "anahtar-123":
            return self._yanit(403, {"hata": "anahtar"})
        yol = self.path.strip("/")
        if yol == "odoolar" and yontem == "GET":
            return self._yanit(200, {"odoolar": [{"id": "deneme"}, {"id": "tekstil"}], "bos_bellek_mb": 9000})
        if yol.startswith("isler/"):
            return self._yanit(200, {"id": yol[6:], "odoo": "tekstil", "durum": "tamam"})
        if yontem == "POST":
            return self._yanit(202, {"id": "abcdef123456", "durum": "calisiyor"})
        return self._yanit(200, {"tamam": True, "yol": yol})

    def _yanit(self, kod, veri):
        govde = json.dumps(veri).encode()
        self.send_response(kod)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def do_GET(self):  # noqa: N802
        self._isle("GET")

    def do_POST(self):  # noqa: N802
        self._isle("POST")

    def log_message(self, *a):
        pass


class PanelTesti(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="panel-web-"))
        SahteAjan.istekler = []
        self.ajan = ThreadingHTTPServer(("127.0.0.1", 0), SahteAjan)
        threading.Thread(target=self.ajan.serve_forever, daemon=True).start()
        self.eski = (P.VERI, P.AJAN_URL, P.AJAN_ANAHTAR, P.PBKDF2_TUR)
        P.VERI = self.tmp
        P.AJAN_URL = f"http://127.0.0.1:{self.ajan.server_address[1]}"
        P.AJAN_ANAHTAR = "anahtar-123"
        P.PBKDF2_TUR = 1000
        P.OTURUMLAR.clear()
        P.DENEMELER.clear()
        P.Panel.log_message = lambda *a, **k: None
        self.panel = ThreadingHTTPServer(("127.0.0.1", 0), P.Panel)
        threading.Thread(target=self.panel.serve_forever, daemon=True).start()
        self.adres = f"http://127.0.0.1:{self.panel.server_address[1]}"
        P.kullanicilari_yaz({
            "platform": {"sifre": P.sifre_ozeti("platform-sifre"), "rol": "platform", "kapsam": "*"},
            "ayse": {"sifre": P.sifre_ozeti("ayse-sifresi1"), "rol": "yonetici", "kapsam": ["deneme"]},
            "destek": {"sifre": P.sifre_ozeti("destek-sifre1"), "rol": "kullanici", "kapsam": ["deneme"]},
        })

    def tearDown(self):
        for s in (self.panel, self.ajan):
            s.shutdown()
            s.server_close()
        P.VERI, P.AJAN_URL, P.AJAN_ANAHTAR, P.PBKDF2_TUR = self.eski
        shutil.rmtree(self.tmp, ignore_errors=True)

    def istek(self, yontem, yol, govde=None, oturum=None, ham=None, basliklar=None):
        veri = ham if ham is not None else (json.dumps(govde).encode() if govde is not None else None)
        b = {"Content-Type": "application/json", **(basliklar or {})}
        if oturum:
            b["Cookie"] = f"panel_oturum={oturum['cerez']}"
            b["X-CSRF"] = oturum["csrf"]
        istek = urllib.request.Request(self.adres + yol, data=veri, method=yontem, headers=b)
        try:
            with urllib.request.urlopen(istek, timeout=30) as yanit:
                return yanit.status, json.loads(yanit.read() or b"{}"), yanit.headers
        except urllib.error.HTTPError as hata:
            return hata.code, json.loads(hata.read() or b"{}"), hata.headers

    def giris(self, ad, sifre):
        kod, veri, basliklar = self.istek("POST", "/api/giris", {"kullanici": ad, "sifre": sifre})
        self.assertEqual(kod, 200, veri)
        cerez = basliklar["Set-Cookie"].split(";")[0].split("=", 1)[1]
        self.assertIn("HttpOnly", basliklar["Set-Cookie"])
        return {"cerez": cerez, "csrf": veri["csrf"]}

    def test_giris_ve_ben(self):
        self.assertEqual(self.istek("POST", "/api/giris", {"kullanici": "ayse", "sifre": "yanlis"})[0], 401)
        o = self.giris("ayse", "ayse-sifresi1")
        kod, veri, _ = self.istek("GET", "/api/ben", oturum=o)
        self.assertEqual((veri["rol"], veri["kapsam"]), ("yonetici", ["deneme"]))
        self.assertIn("deploy", veri["yetkiler"])
        self.assertNotIn("terminal", veri["yetkiler"])
        self.assertEqual(self.istek("GET", "/api/ben")[0], 401)

    def test_kapsam_ve_yetki(self):
        ayse = self.giris("ayse", "ayse-sifresi1")
        kod, veri, _ = self.istek("GET", "/api/ajan/odoolar", oturum=ayse)
        self.assertEqual([o["id"] for o in veri["odoolar"]], ["deneme"])
        self.assertNotIn("bos_bellek_mb", veri)
        self.assertEqual(self.istek("GET", "/api/ajan/odoolar/tekstil", oturum=ayse)[0], 404)
        self.assertEqual(self.istek("GET", "/api/ajan/bulunanlar", oturum=ayse)[0], 403)
        self.assertEqual(self.istek("GET", "/api/ajan/isler/abcdef123456", oturum=ayse)[0], 404)  # iş tekstil'in
        self.assertEqual(self.istek("GET", "/api/ajan/isler", oturum=ayse)[0], 400)
        self.assertEqual(self.istek("POST", "/api/ajan/odoolar/deneme/production/deploy", {}, oturum=ayse)[0], 202)
        istek = SahteAjan.istekler[-1]
        self.assertEqual(istek["basliklar"]["X-Panel-Kullanici"], "ayse")
        self.assertEqual(istek["basliklar"]["X-Ajan-Anahtar"], "anahtar-123")
        destek = self.giris("destek", "destek-sifre1")
        self.assertEqual(self.istek("POST", "/api/ajan/odoolar/deneme/production/deploy", {}, oturum=destek)[0], 403)
        self.assertEqual(self.istek("POST", "/api/ajan/odoolar/deneme/production/yedek", {}, oturum=destek)[0], 202)
        self.assertEqual(self.istek("GET", "/api/ajan/gece-yedegi", oturum=destek)[0], 404)
        platform = self.giris("platform", "platform-sifre")
        kod, veri, _ = self.istek("GET", "/api/ajan/odoolar", oturum=platform)
        self.assertEqual(len(veri["odoolar"]), 2)
        self.assertEqual(self.istek("GET", "/api/ajan/isler/abcdef123456", oturum=platform)[0], 200)

    def test_csrf_ve_kurulan_odoo_kapsama_eklenir(self):
        ayse = self.giris("ayse", "ayse-sifresi1")
        sahte = {"cerez": ayse["cerez"], "csrf": "yanlis"}
        self.assertEqual(self.istek("POST", "/api/ajan/odoolar", {"id": "yeni-firma"}, oturum=sahte)[0], 403)
        self.assertEqual(self.istek("POST", "/api/ajan/odoolar", {"id": "yeni-firma"}, oturum=ayse)[0], 202)
        self.assertEqual(P.kullanicilari_oku()["ayse"]["kapsam"], ["deneme", "yeni-firma"])
        kayitlar = [json.loads(s) for s in (self.tmp / "islem.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(k["olay"] == "POST odoolar" and k.get("odoo") == "yeni-firma" for k in kayitlar))

    def test_kullanici_yonetimi_sinirlari(self):
        ayse = self.giris("ayse", "ayse-sifresi1")
        kod, veri, _ = self.istek("POST", "/api/kullanicilar", {"ad": "x.plat", "rol": "platform"}, oturum=ayse)
        self.assertEqual(kod, 400)
        kod, veri, _ = self.istek("POST", "/api/kullanicilar", {"ad": "can", "rol": "kullanici",
                                                                 "kapsam": ["tekstil"]}, oturum=ayse)
        self.assertEqual(kod, 400)
        kod, veri, _ = self.istek("POST", "/api/kullanicilar", {"ad": "can", "rol": "kullanici",
                                                                 "kapsam": ["deneme"]}, oturum=ayse)
        self.assertEqual((kod, veri["kapsam"]), (200, ["deneme"]))
        self.assertGreaterEqual(len(veri["sifre"]), 10)
        self.assertEqual(self.istek("POST", "/api/kullanicilar/platform/sil", {}, oturum=ayse)[0], 400)
        kod, veri, _ = self.istek("GET", "/api/kullanicilar", oturum=ayse)
        self.assertEqual(sorted(k["ad"] for k in veri["kullanicilar"]), ["ayse", "can", "destek"])
        destek = self.giris("destek", "destek-sifre1")
        self.assertEqual(self.istek("GET", "/api/kullanicilar", oturum=destek)[0], 403)

    def test_webhook_ve_zip_gecisi(self):
        govde = b'{"ref": "refs/heads/main"}'
        kod, veri, _ = self.istek("POST", "/webhook/github", ham=govde,
                                  basliklar={"X-Hub-Signature-256": "sha256=abc", "X-GitHub-Event": "push"})
        self.assertEqual(kod, 202)
        istek = SahteAjan.istekler[-1]
        self.assertEqual((istek["yol"], istek["govde"]), ("/webhook/github", govde))
        self.assertEqual(istek["basliklar"]["X-Hub-Signature-256"], "sha256=abc")
        ayse = self.giris("ayse", "ayse-sifresi1")
        zip_veri = b"PK\x03\x04" + b"0" * 5000
        kod, veri, _ = self.istek("POST", "/api/ajan/odoolar/deneme/staging/zip?dosya=a%20b.zip&hedef=pr&mesaj=%C3%A7",
                                  ham=zip_veri, oturum=ayse, basliklar={"Content-Type": "application/zip"})
        self.assertEqual(kod, 202)
        istek = SahteAjan.istekler[-1]
        self.assertEqual(istek["govde"], zip_veri)
        self.assertIn("dosya=a%20b.zip", istek["yol"])
        self.assertIn("hedef=pr", istek["yol"])

    def test_log_parametresi_ve_kendi_denetim_kaydi(self):
        ayse = self.giris("ayse", "ayse-sifresi1")
        self.istek("GET", "/api/ajan/odoolar/deneme/production/loglar?satir=500&kotu=1", oturum=ayse)
        self.assertEqual(SahteAjan.istekler[-1]["yol"], "/odoolar/deneme/production/loglar?satir=500")
        kod, veri, _ = self.istek("GET", "/api/denetim", oturum=ayse)
        self.assertTrue(any(k["olay"] == "GIRIS" and k["kullanici"] == "ayse" for k in veri["kayitlar"]))
        self.assertFalse(any(k["kullanici"] == "platform" for k in veri["kayitlar"]))
        self.assertEqual(self.istek("GET", "/api/ajan/odoolar/tekstil/production/loglar", oturum=ayse)[0], 404)

    def test_statik_dosya_yolu_kacisi(self):
        self.assertEqual(self.istek("GET", "/../panel.py")[0], 404)
        self.assertEqual(self.istek("GET", "/static/../panel.py")[0], 404)
