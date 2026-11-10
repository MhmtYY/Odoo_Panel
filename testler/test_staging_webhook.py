"""Staging (oluştur, yenile, yedekten aç, sil), webhook, production'a alma, bağlanan kurulum."""
import hashlib
import hmac
import json
from pathlib import Path

from ajan.hata import Hata

from .yardimci import Temel, modul


def imzala(sir, govde):
    return "sha256=" + hmac.new(sir.encode(), govde, hashlib.sha256).hexdigest()


class StagingTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.ana = self.commit(modul("mod_a"), "[ADD] mod_a")
        self.st_commit = self.commit({"mod_a/models/a.py": "x = 1\n"}, "[IMP] staging", dal="staging")
        self.kurulu_yap("pnl_deneme", "mod_a")
        self.depo_bagla(staging="staging")
        self.assertEqual(self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))["durum"], "tamam")

    def test_olustur_notrlestir_ve_dal_deploy(self):
        sonuc = self.is_sonucu(self.s.staging.olustur("deneme", "tester"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        st = self.s.ortamlar.gerekli("deneme", "staging")
        self.assertEqual(st["konteyner"], "pnl-deneme-staging")
        self.assertEqual(st["db_adi"], "pnl_deneme_staging")
        self.assertEqual(st["adres"], "https://deneme-staging.panel.vekosis.com")
        self.assertEqual(st["notr"]["notr"], "True")
        self.assertIn("pnl_deneme_staging", self.komut.notrlestirilen)
        self.assertIn(("pnl_deneme_staging", "pnl_deneme"), self.komut.yuklenen_dokumler)
        self.assertTrue((self.ayar.kenar_tenants / "deneme-staging.panel.vekosis.com").exists())
        conf = Path(st["conf"]).read_text()
        self.assertIn("db_user = pnl_deneme_st", conf)
        self.assertNotIn("pnl_deneme\n", conf.replace("pnl_deneme_", ""))
        # staging dalı sıraya alınıp deploy edildi
        self.assertEqual(st["commit"], self.st_commit)
        d = self.s.deploylar.kayit_oku("deneme", "staging", 1)
        self.assertEqual(d["durum"], "tamam")
        self.assertNotIn("yedek", d)  # staging'de deploy öncesi yedek alınmaz
        sql = [c for c in self.komut.bul("psql") if "pnl_deneme_staging" in " ".join(c)]
        self.assertTrue(sql)

    def test_ikinci_kez_olusturulamaz_ve_yenile(self):
        self.is_sonucu(self.s.staging.olustur("deneme"))
        with self.assertRaises(Hata) as h:
            self.s.staging.olustur("deneme")
        self.assertEqual(h.exception.kod, 409)
        once = len(self.komut.notrlestirilen)
        sonuc = self.is_sonucu(self.s.staging.yenile("deneme"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(len(self.komut.notrlestirilen), once + 1)
        etiketler = [y["etiket"] for y in self.s.yedekler.liste("deneme", "staging")]
        self.assertIn("YENILEME-ONCESI", etiketler)
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "staging")["veri_kaynak"]["tur"], "production")

    def test_yedekten_ac_ve_sil(self):
        yedek = self.s.yedekler.liste("deneme", "production")[0]["dosya"]
        sonuc = self.is_sonucu(self.s.staging.yedekten_ac("deneme", yedek))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        st = self.s.ortamlar.gerekli("deneme", "staging")
        self.assertEqual(st["veri_kaynak"], {"tur": "yedek", "dosya": yedek, "tarih": st["veri_kaynak"]["tarih"]})
        sonuc = self.is_sonucu(self.s.staging.sil("deneme"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertIsNone(self.s.ortamlar.oku("deneme", "staging"))
        self.assertNotIn("pnl-deneme-staging", self.komut.konteynerler)
        self.assertNotIn(("vtest-postgres", "pnl_deneme_staging"), self.komut.veritabanlari)
        self.assertFalse((self.ayar.kenar_tenants / "deneme-staging.panel.vekosis.com").exists())

    def test_production_al_app_yokken_commit_sabitlenir(self):
        self.is_sonucu(self.s.staging.olustur("deneme"))
        self.assertEqual([c["sha"] for c in self.s.deploylar.onde("deneme")], [self.st_commit])
        sonuc = self.is_sonucu(self.s.deploylar.production_al("deneme", self.s.github))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "production")["commit"], self.st_commit)
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertTrue(d["dal_disi"])
        self.assertEqual(self.s.deploylar.onde("deneme"), [])


class WebhookTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.commit(modul("mod_a"), "[ADD] mod_a")
        self.commit({"mod_a/models/a.py": "x = 1\n"}, "st", dal="staging")
        self.kurulu_yap("pnl_deneme", "mod_a")
        self.depo_bagla(staging="staging")
        self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))
        self.is_sonucu(self.s.staging.olustur("deneme"))
        self.sir = "webhook-sirri-123456"
        (self.ayar.ayar_dizin / "webhook_sirri").write_text(self.sir)

    def push(self, dal, sha, teslim="t1", sir=None):
        govde = json.dumps({"ref": f"refs/heads/{dal}", "after": sha, "repository": {"full_name": "sahip/depo"},
                            "head_commit": {"message": "[FIX] mod_a: düzeltme\n\nayrıntı", "author": {"name": "Ayşe"}}}
                           ).encode()
        return self.s.webhook.isle(govde, {"X-Hub-Signature-256": imzala(sir or self.sir, govde),
                                           "X-GitHub-Event": "push", "X-GitHub-Delivery": teslim})

    def test_imzasiz_istek_reddedilir(self):
        with self.assertRaises(Hata) as h:
            self.push("staging", "a" * 40, sir="yanlis-sir-123456")
        self.assertEqual(h.exception.kod, 401)

    def test_staging_otomatik_production_bekler(self):
        sha = self.commit({"mod_a/models/a.py": "x = 2\n"}, "[FIX] staging", dal="staging")
        yanit = self.push("staging", sha)
        self.assertEqual(yanit["ortamlar"][0]["durum"], "deploy")
        st = self.s.ortamlar.gerekli("deneme", "staging")
        self.assertEqual(st["commit"], sha)
        d = self.s.deploylar.kayitlar("deneme", "staging")[0]
        self.assertEqual((d["tetik"], d["durum"]), ("webhook", "tamam"))
        # aynı teslim ikinci kez işlenmez
        self.assertEqual(self.push("staging", sha)["durum"], "tekrar")
        # production dalı elle kipinde: yalnız bekleyen olarak işaretlenir
        ana = self.commit({"mod_a/models/a.py": "x = 9\n"}, "[FIX] main")
        yanit = self.push("main", ana, teslim="t2")
        self.assertEqual(yanit["ortamlar"][0]["durum"], "bekliyor")
        pr = self.s.ortamlar.gerekli("deneme", "production")
        self.assertEqual(pr["bekleyen"]["commit"], ana)
        self.assertEqual(pr["bekleyen"]["yazar"], "Ayşe")
        self.assertNotEqual(pr["commit"], ana)

    def test_ping_ve_dal_silme(self):
        govde = b'{"zen": "x"}'
        self.assertEqual(self.s.webhook.isle(govde, {"X-Hub-Signature-256": imzala(self.sir, govde),
                                                     "X-GitHub-Event": "ping"})["olay"], "ping")
        govde = json.dumps({"ref": "refs/heads/staging", "after": "0" * 40, "deleted": True,
                            "repository": {"full_name": "sahip/depo"}}).encode()
        yanit = self.s.webhook.isle(govde, {"X-Hub-Signature-256": imzala(self.sir, govde), "X-GitHub-Event": "push"})
        self.assertEqual(yanit["durum"], "yok sayildi")


class BaglamaTesti(Temel):
    def setUp(self):
        super().setUp()
        vt = self.ayar.vtest_kok / "tenants" / "musteri"
        (vt / "addons" / "ozel_modul").mkdir(parents=True)
        (vt / "addons" / "ozel_modul" / "__manifest__.py").write_text("{'name': 'x', 'version': '20.0.1.0.0'}")
        (vt / "odoo.conf").write_text("[options]\ndb_host = vtest-postgres\ndb_user = t_musteri\ndb_password = gizli123\n"
                                      "db_name = musteri\ndbfilter = ^musteri$\n"
                                      "addons_path = /mnt/vekosis-addons,/mnt/extra-addons\nworkers = 2\n"
                                      "email_from = bilgi@example.com\nlimit_time_real = 1500\n")
        self.ayar.kenar_tenants.mkdir(parents=True)
        (self.ayar.kenar_tenants.parent / "Caddyfile").write_text(
            "erp.vekosis.com {\n    reverse_proxy /websocket* erp20-odoo:8072\n    reverse_proxy erp20-odoo:8069 {\n"
            "        request_buffers 16MB\n    }\n}\n*.test.vekosis.com {\n"
            "    reverse_proxy odoo-{labels.3}:8069 {\n    }\n}\n")
        self.komut.konteynerler.update({"odoo-musteri": "running", "vtest-postgres": "running", "vtest-panel": "running"})
        self.komut.veritabanlari[("vtest-postgres", "musteri")] = {"base", "sale", "stock"}
        self.komut.inceleme = {
            "odoo-musteri": {
                "Name": "/odoo-musteri", "State": {"Status": "running"},
                "Config": {"Image": "vekosis/test20:20261108-1", "Env": [], "Labels": {
                    "com.docker.compose.project": "odoo-musteri",
                    "com.docker.compose.project.working_dir": str(vt),
                    "com.docker.compose.service": "odoo"}},
                "Mounts": [
                    {"Type": "bind", "Source": str(vt / "odoo.conf"), "Destination": "/etc/odoo/odoo.conf"},
                    {"Type": "bind", "Source": str(vt / "addons"), "Destination": "/mnt/extra-addons"},
                    {"Type": "volume", "Name": "odoo-musteri-data", "Destination": "/var/lib/odoo"}],
                "NetworkSettings": {"Networks": {"vtest": {}}}},
            "vtest-postgres": {"Name": "/vtest-postgres", "State": {"Status": "running"},
                               "Config": {"Image": "postgres:17", "Env": ["POSTGRES_PASSWORD=x"], "Labels": {}},
                               "Mounts": []},
            "vtest-panel": {"Name": "/vtest-panel", "State": {"Status": "running"},
                            "Config": {"Image": "vekosis/test-panel:1.0", "Labels": {}}, "Mounts": []},
        }

    def test_bulunanlar_ve_bagla(self):
        bulunan = self.s.kurulum.bulunanlar()
        self.assertEqual([b["konteyner"] for b in bulunan], ["odoo-musteri"])
        self.assertEqual(bulunan[0]["kaynak"], "vtest")
        self.assertEqual(bulunan[0]["adres"], "https://musteri.test.vekosis.com")
        sonuc = self.s.kurulum.bagla({"konteyner": "odoo-musteri", "id": "musteri", "firma": "Müşteri"})
        o = sonuc["production"]
        self.assertEqual((o["yonetim"], o["db_adi"], o["db_su"], o["birim"]),
                         ("bagli", "musteri", "postgres", "odoo-musteri-data"))
        self.assertEqual([h for _, h in o["kesif"]["kod_baglamalari"]], ["/mnt/extra-addons"])
        self.assertEqual(o["addons_yollari"], ["/mnt/vekosis-addons"])
        self.assertEqual(o["adres"], "https://musteri.test.vekosis.com")
        self.assertEqual(self.s.kurulum.bulunanlar()[0]["bagli_odoo"], "musteri")
        # bağlarken hiçbir şey durdurulmadı / yeniden başlatılmadı / compose'a dokunulmadı
        self.assertFalse([c for c in self.komut.cagrilar if c[1] in ("stop", "start", "restart", "compose", "rm")])
        with self.assertRaises(Hata) as h:
            self.s.kurulum.bagla({"konteyner": "odoo-musteri", "id": "musteri2"})
        self.assertEqual(h.exception.kod, 409)

    def test_bagliya_deploy_yok_durdurma_izinle(self):
        self.s.kurulum.bagla({"konteyner": "odoo-musteri", "id": "musteri"})
        with self.assertRaises(Hata):
            self.s.deploylar.baslat("musteri", "production")
        with self.assertRaises(Hata) as h:
            self.s.durdur_baslat("musteri", "production", "durdur")
        self.assertEqual(h.exception.kod, 403)
        od = self.s.odoolar.gerekli("musteri")
        od["islemler_acik"] = True
        self.s.odoolar.yaz(od)
        sonuc = self.is_sonucu(self.s.durdur_baslat("musteri", "production", "durdur"))
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertEqual(self.komut.konteynerler["odoo-musteri"], "exited")
        self.assertTrue(self.komut.bul("docker stop --time 30 odoo-musteri"))

    def test_bagli_production_icin_staging(self):
        self.s.kurulum.bagla({"konteyner": "odoo-musteri", "id": "musteri"})
        yedek = self.is_sonucu(self.s.yedek_al("musteri", "production"))
        self.assertEqual(yedek["durum"], "tamam", yedek.get("cikti"))
        self.assertTrue(self.s.yedekler.liste("musteri", "production"))
        sonuc = self.is_sonucu(self.s.staging.olustur("musteri"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        st = self.s.ortamlar.gerekli("musteri", "staging")
        self.assertEqual(st["yonetim"], "panel")
        self.assertEqual(st["adres"], "https://musteri-staging.panel.vekosis.com")
        self.assertTrue((Path(st["ek_addons"]) / "ozel_modul" / "__manifest__.py").exists())
        conf = Path(st["conf"]).read_text()
        self.assertIn("limit_time_real = 1500", conf)  # production'ın kendi sınırı korunur
        self.assertNotIn("email_from", conf)
        self.assertNotIn("gizli123", conf)
        self.assertIn(("pnl_musteri_staging", "musteri"), self.komut.yuklenen_dokumler)
        # production'a (bağlanan) panelden geri yükleme yok
        with self.assertRaises(Hata) as h:
            self.s.geri_yukle("musteri", "production", self.s.yedekler.liste("musteri", "production")[0]["dosya"],
                              "musteri.test.vekosis.com")
        self.assertEqual(h.exception.kod, 403)
