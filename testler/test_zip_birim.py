"""Zip -> depo akışı ve birim testleri (uyumluluk, zip incelemesi, gereksinimler, GitHub, HTTP)."""
import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

from ajan import pykatman, sunucu, uyumluluk, zipdepo
from ajan.github import GitHub, imza_dogru
from ajan.hata import Hata

from .sahte import SahteKomut, sahte_http
from .yardimci import Temel, manifest, modul


def zip_yap(dosyalar, baglanti=None):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for ad, metin in dosyalar.items():
            z.writestr(ad, metin)
        if baglanti:
            bilgi = zipfile.ZipInfo(baglanti)
            bilgi.external_attr = (0o120777 << 16)
            z.writestr(bilgi, "/etc/passwd")
    return tampon.getvalue()


class ZipDepoTesti(Temel):
    app = True

    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.ana = self.commit(modul("mod_a"), "[ADD] mod_a")
        self.kurulu_yap("pnl_deneme", "mod_a")
        self.depo_bagla(kip_prod="webhook", baglanti="app")
        self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))

    def uzak_git(self, *args):
        return self._git("--git-dir", str(self.uzak), *args)

    def test_dala_dogrudan_commit_ve_deploy(self):
        veri = zip_yap({f"ornek_kalite/{k.split('/', 1)[1]}": v for k, v in modul("ornek_kalite").items()})
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "ornek_kalite.zip", "dal",
                                                     "[ADD] ornek_kalite: kalite kontrol", "tester"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(self.uzak_git("log", "-1", "--format=%s", "main"), "[ADD] ornek_kalite: kalite kontrol")
        self.assertIn("ornek_kalite", self.uzak_git("show", "main:ornek_kalite/__manifest__.py"))
        self.assertIn("mod_a", self.uzak_git("ls-tree", "--name-only", "main"))  # diğer modüller yerinde
        yeni = self.uzak_git("rev-parse", "main")
        self.assertEqual(sonuc["sonuc"]["deploylar"][0]["durum"], "deploy")
        o = self.s.ortamlar.gerekli("deneme", "production")
        self.assertEqual(o["commit"], yeni)
        d = self.s.deploylar.kayitlar("deneme", "production")[0]
        self.assertEqual((d["tetik"], d["yeni_moduller"]), ("zip", ["ornek_kalite"]))
        # aynı zip ikinci kez: değişiklik yok
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "ornek_kalite.zip", "dal", "", "t"))
        self.assertFalse(sonuc["sonuc"]["degisiklik"])

    def test_pr_yolu(self):
        dosyalar = dict(modul("mod_a"))
        dosyalar["mod_a/models/yeni.py"] = "z = 1\n"
        veri = zip_yap(dosyalar)
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "mod_a.zip", "pr", "", "tester"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(sonuc["sonuc"]["pr"]["no"], 12)
        dal = self.s.odoolar.gerekli("deneme")["zip_pr"][0]["dal"]
        self.assertTrue(dal.startswith("panel/zip-mod-a-"))
        self.assertIn("models/yeni.py", self.uzak_git("ls-tree", "-r", "--name-only", dal))
        self.assertEqual(self.uzak_git("rev-parse", "main"), self.ana)  # ana dal değişmedi
        pr_istegi = [c for c in self.http.cagrilar if c[0] == "POST" and c[1].endswith("/pulls")][0]
        self.assertEqual((pr_istegi[2]["base"], pr_istegi[2]["head"]), ("main", dal))
        uyarilar = sonuc.get("uyarilar") or []
        self.assertTrue(any("sürüm numarası artırılmamış" in u for u in uyarilar), uyarilar)

    def test_uyumsuz_ve_guvensiz_zip(self):
        veri = zip_yap(modul("mod_x", surum="19.0.1.0.0"))
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "x.zip", "dal", "", "t"))
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("19.0 serisi", sonuc["hata"])
        self.assertEqual(self.uzak_git("rev-parse", "main"), self.ana)
        veri = zip_yap(modul("mod_y"), baglanti="mod_y/kotu")
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "y.zip", "dal", "", "t"))
        self.assertIn("sembolik bağlantı", sonuc["hata"])
        veri = zip_yap({**modul("mod_z"), "mod_z/data/anahtar.txt":
                        "-----BEGIN OPENSSH PRIVATE KEY-----\nabc\n-----END OPENSSH PRIVATE KEY-----\n"})
        sonuc = self.is_sonucu(self.s.zipdepo.yukle("deneme", "production", veri, "z.zip", "dal", "", "t"))
        self.assertIn("özel anahtar", sonuc["hata"])

    def test_deploy_key_ile_zip_kapali(self):
        od = self.s.odoolar.gerekli("deneme")
        od["depo"]["baglanti"] = "anahtar"
        self.s.odoolar.yaz(od)
        with self.assertRaises(Hata) as h:
            self.s.zipdepo.yukle("deneme", "production", b"PK", "a.zip", "dal", "", "t")
        self.assertIn("GitHub App", h.exception.mesaj)


class BirimTesti(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="panel-birim-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def modul_yaz(self, ad, metin, ek=None):
        klasor = self.tmp / "kod" / ad
        klasor.mkdir(parents=True)
        (klasor / "__manifest__.py").write_text(metin)
        (klasor / "__init__.py").write_text("")
        for yol, icerik in (ek or {}).items():
            (klasor / yol).parent.mkdir(parents=True, exist_ok=True)
            (klasor / yol).write_text(icerik)

    def test_uyumluluk_kurulu_engel_kurulmayan_uyari(self):
        self.modul_yaz("a", manifest("a", depends=("base", "yok_modul")))
        self.modul_yaz("b", manifest("b", depends=("yok_modul",)))
        self.modul_yaz("c", manifest("c", data=("views/v.xml", "views/eksik.xml")), {"views/v.xml": "<odoo><record>"})
        rapor = uyumluluk.denetle(uyumluluk.klasor_modulleri(self.tmp / "kod"), seri="20.0", mevcut={"base"},
                                  kurulu={"a", "c"})
        self.assertFalse(rapor["gecti"])
        self.assertEqual(rapor["moduller"]["a"]["durum"], "engel")
        self.assertEqual(rapor["moduller"]["b"]["durum"], "uyari")
        notlar = " ".join(rapor["moduller"]["c"]["notlar"])
        self.assertIn("XML hatası: views/v.xml", notlar)
        self.assertIn("Manifest'teki dosya yok: views/eksik.xml", notlar)

    def test_zip_inceleme(self):
        with self.assertRaises(Hata):
            zipdepo.incele(zip_yap({"../disari.py": "x"}), "a.zip", self.tmp / "c1")
        rapor = zipdepo.incele(zip_yap({"__manifest__.py": manifest("x"), "__init__.py": ""}),
                               "ornek_modul-20.0.1.0.0.zip", self.tmp / "c2")
        self.assertEqual(rapor["moduller"], ["ornek_modul"])
        rapor = zipdepo.incele(zip_yap({"depo-main/mod_a/__manifest__.py": manifest("mod_a"),
                                        "depo-main/mod_a/__init__.py": "",
                                        "depo-main/mod_a/__pycache__/x.pyc": "x"}), "depo-main.zip", self.tmp / "c3")
        self.assertEqual(rapor["moduller"], ["mod_a"])
        self.assertEqual(rapor["dosya"], 2)
        rapor = zipdepo.incele(zip_yap({"mod_m/__manifest__.py": manifest("mod_m"), "mod_m/__init__.py": "",
                                        "mod_m/ayar.py":"password = 'cokgizli99'\n"}), "m.zip", self.tmp / "c4")
        self.assertEqual(rapor["engeller"], [])
        self.assertTrue(rapor["uyarilar"])
        with self.assertRaises(Hata):
            zipdepo.incele(b"zip degil", "a.zip", self.tmp / "c5")

    def test_gereksinimler(self):
        self.assertEqual(pykatman.gereksinimleri_temizle("# yorum\nxlsxwriter==3.2.0\nphonenumbers>=8,<9  # not\n\n"),
                         ["xlsxwriter==3.2.0", "phonenumbers>=8,<9"])
        for kotu in ("git+https://x/y.git", "-e .", "--index-url https://x", "paket @ https://x/p.whl", "a; rm -rf /"):
            with self.assertRaises(Hata, msg=kotu):
                pykatman.gereksinimleri_temizle(kotu)

    def test_github_imza_ve_jeton_onbellegi(self):
        self.assertTrue(imza_dogru("s", b"{}", "sha256=" + __import__("hmac").new(b"s", b"{}", "sha256").hexdigest()))
        self.assertFalse(imza_dogru("s", b"{}", "sha256=00"))
        self.assertFalse(imza_dogru("", b"{}", "sha256=00"))
        from ajan.ayar import Ayar
        ayar = Ayar(kok=self.tmp / "kok")
        ayar.klasorleri_kur()
        (ayar.ayar_dizin / "github_app.json").write_text('{"app_id": 5, "anahtar": "a.pem"}')
        (ayar.ayar_dizin / "a.pem").write_text("x")
        http = sahte_http({("GET", "/installation"): (200, {"id": 9}),
                           ("POST", "/access_tokens"): (201, {"token": "ghs_xyz123456", "expires_at": "2099-01-01T00:00:00Z"})})
        komut = SahteKomut()
        gh = GitHub(ayar, komut, http=http)
        self.assertEqual(gh.jeton("sahip/depo"), "ghs_xyz123456")
        self.assertEqual(gh.jeton("sahip/diger"), "ghs_xyz123456")
        self.assertEqual(len(http.cagrilar), 2)  # kurulum ve jeton bir kez
        self.assertEqual(komut.maskele("jeton ghs_xyz123456"), "jeton ***")


class HttpTesti(Temel):
    def setUp(self):
        super().setUp()
        self.ayar.kuru = True  # IP denetimi yerelde atlanır; anahtar denetimi yapılır
        sunucu.Istek.servis = self.s
        sunucu.Istek.anahtar = "ajan-anahtari-123456"
        sunucu.Istek.rota_listesi = sunucu.rotalar(self.s)
        sunucu.Istek.log_message = lambda *a, **k: None
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), sunucu.Istek)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.adres = f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def istek(self, yontem, yol, govde=None, anahtar="ajan-anahtari-123456"):
        veri = json.dumps(govde).encode() if govde is not None else None
        istek = urllib.request.Request(self.adres + yol, data=veri, method=yontem,
                                       headers={"X-Ajan-Anahtar": anahtar, "X-Panel-Kullanici": "tester",
                                                "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(istek, timeout=60) as yanit:
                return yanit.status, json.loads(yanit.read())
        except urllib.error.HTTPError as hata:
            return hata.code, json.loads(hata.read())

    def test_anahtar_ve_rotalar(self):
        self.assertEqual(self.istek("GET", "/saglik", anahtar="yanlis")[0], 403)
        kod, veri = self.istek("GET", "/saglik")
        self.assertEqual((kod, veri["alan"]), (200, "panel.vekosis.com"))
        self.assertEqual(self.istek("GET", "/yok")[0], 404)
        self.assertEqual(self.istek("POST", "/odoolar", {"id": "X!"})[0], 400)
        kod, is_kaydi = self.istek("POST", "/odoolar", {"id": "deneme", "baslangic": "bos",
                                                         "imaj": "vekosis/test20:20261108-1"})
        self.assertEqual(kod, 202)
        kod, veri = self.istek("GET", f"/isler/{is_kaydi['id']}")
        self.assertEqual(veri["durum"], "tamam")
        self.assertEqual(veri["kullanici"], "tester")
        kod, veri = self.istek("GET", "/odoolar")
        self.assertEqual(veri["odoolar"][0]["id"], "deneme")
        self.assertEqual(veri["odoolar"][0]["ortamlar"]["production"]["kaynak"]["bellek_mb"], 512)
        self.assertEqual(self.istek("GET", "/odoolar/deneme/production/yedekler/../../ayar")[0], 404)
        kod, veri = self.istek("POST", "/odoolar/deneme/production/geri-yukle", {"dosya": "x.tar", "onay": "x"})
        self.assertEqual(kod, 400)
