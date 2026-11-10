"""Arayüzün kullandığı uçlar: modül listesi, loglar, Odoo silme, depo bağlantısını kaldırma."""
from ajan.hata import Hata

from .yardimci import Temel, modul


class ArayuzUclariTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.commit({**modul("mod_a"), **modul("mod_b")}, "[ADD] mod_a, mod_b")
        self.kurulu_yap("pnl_deneme", "mod_a")
        self.depo_bagla(staging="staging")
        self.commit({"mod_a/models/a.py": "x = 1\n"}, "st", dal="staging")
        self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))

    def test_moduller(self):
        v = self.s.moduller("deneme", "production")
        satirlar = {m["ad"]: m for m in v["moduller"]}
        self.assertEqual(sorted(satirlar), ["mod_a", "mod_b"])
        self.assertTrue(satirlar["mod_a"]["kurulu"])
        self.assertFalse(satirlar["mod_b"]["kurulu"])
        self.assertEqual(satirlar["mod_a"]["kaynak"], "depo")
        self.assertGreaterEqual(v["kurulu_sayisi"], 2)

    def test_loglar(self):
        v = self.s.loglar("deneme", "production", 80)
        self.assertEqual(v["konteyner"], "pnl-deneme")
        self.assertTrue(any("WARNING" in s for s in v["satirlar"]))
        self.assertTrue(self.komut.bul("docker logs --tail 80 --timestamps pnl-deneme"))
        with self.assertRaises(Hata):
            self.s.loglar("deneme", "staging")

    def test_depo_kaldir(self):
        self.s.odoolar.depo_kaldir(self.s.odoolar.gerekli("deneme"))
        self.assertIsNone(self.s.odoolar.gerekli("deneme")["depo"])
        with self.assertRaises(Hata):
            self.s.deploylar.baslat("deneme", "production")
        with self.assertRaises(Hata):
            self.s.odoolar.depo_kaldir(self.s.odoolar.gerekli("deneme"))

    def test_odoo_silme(self):
        self.is_sonucu(self.s.staging.olustur("deneme"))
        with self.assertRaises(Hata):
            self.s.kurulum.sil("deneme", "yanlis.adres", self.s.staging, self.s.yedekler)
        sonuc = self.is_sonucu(self.s.kurulum.sil("deneme", "deneme.panel.vekosis.com", self.s.staging, self.s.yedekler))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertIsNone(self.s.odoolar.oku("deneme"))
        for ad in ("pnl-deneme", "pnl-deneme-staging"):
            self.assertNotIn(ad, self.komut.konteynerler)
        for db in ("pnl_deneme", "pnl_deneme_staging"):
            self.assertNotIn(("vtest-postgres", db), self.komut.veritabanlari)
        self.assertFalse((self.ayar.kenar_tenants / "deneme.panel.vekosis.com").exists())
        yedekler = self.s.yedekler.liste("deneme", "production")
        self.assertEqual(yedekler[0]["etiket"], "SILINMEDEN-ONCE")
        self.assertTrue(list((self.ayar.kok / "silinenler").glob("deneme-*")))

    def test_bagli_kurulum_silinmez(self):
        od = self.s.odoolar.gerekli("deneme")
        od["tur"] = "bagli"
        self.s.odoolar.yaz(od)
        with self.assertRaises(Hata) as h:
            self.s.kurulum.sil("deneme", "deneme.panel.vekosis.com", self.s.staging, self.s.yedekler)
        self.assertIn("bağlantısı kaldırılır", h.exception.mesaj)
