"""Platformdan şablon, şablondan kurulum, hazır imaj listesi."""
from pathlib import Path

from ajan.hata import Hata
from ajan.sablon import temizlik_sql

from .yardimci import Temel, modul

IMAJ = "vekosis/test20:20261108-1"


class SablonTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.commit(modul("mod_a"), "[ADD] mod_a")
        self.kurulu_yap("pnl_deneme", "mod_a", "sale")
        self.depo_bagla()
        self.assertEqual(self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))["durum"], "tamam")
        self.pr = self.s.ortamlar.gerekli("deneme", "production")

    def sablon(self, ad="temel", tur="moduller", **ek):
        sonuc = self.is_sonucu(self.s.sablonlar.olustur("deneme", "production", {"ad": ad, "tur": tur, **ek}, "tester"))
        return sonuc

    def kur(self, ad, sablon):
        return self.is_sonucu(self.s.kurulum.kur({"id": ad, "firma": "Yeni A.Ş.", "baslangic": "panel-sablon", "sablon": sablon}, "tester"))

    def test_yalniz_modul_sablonu_ve_kurulum(self):
        self.assertEqual(self.sablon(baslik="İmalat", aciklama="Temel paket")["durum"], "tamam")
        dizin = self.s.sablonlar.dizin("temel")
        self.assertTrue((dizin / "kod" / "mod_a" / "__manifest__.py").is_file())
        self.assertFalse((dizin / "veritabani.dump").exists())
        self.assertFalse((dizin / "kod" / ".hazir").exists())
        bilgi = self.s.sablonlar.liste()[0]
        self.assertEqual((bilgi["baslik"], bilgi["tur"], bilgi["kaynak_odoo"], bilgi["imaj"], bilgi["imaj_var"]),
                         ("İmalat", "moduller", "deneme", self.pr["imaj"], True))
        self.assertIn("mod_a", bilgi["moduller"])

        sonuc = self.kur("yeni", "temel")
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        o = self.s.ortamlar.gerekli("yeni", "production")
        od = self.s.odoolar.gerekli("yeni")
        self.assertEqual((od["baslangic"], od["sablon"], od["depo"]), ("panel-sablon", "temel", None))
        self.assertEqual(o["imaj"], self.pr["imaj"])
        self.assertTrue(self._ek(o, "mod_a/__manifest__.py").is_file())
        self.assertEqual(self.komut.veritabanlari[("vtest-postgres", "pnl_yeni")], set(bilgi["moduller"]))
        self.assertEqual(self.komut.yuklenen_dokumler, [])

    @staticmethod
    def _ek(o, yol):
        return Path(o["ek_addons"]) / yol

    def test_veri_sablonu_temizlenir_ve_gecici_kalmaz(self):
        birimler = set(self.komut.birimler)
        odoolar = {p.name for p in self.ayar.odoolar.iterdir()}
        self.assertEqual(self.sablon(tur="veri", onay=True)["durum"], "tamam")
        dizin = self.s.sablonlar.dizin("temel")
        self.assertTrue((dizin / "veritabani.dump").is_file())
        self.assertTrue((dizin / "filestore.tar.gz").is_file())
        self.assertFalse((dizin / "kaynak.dump").exists())
        # temizlik geçici kopyada yapıldı, kaynağa dokunulmadı
        self.assertEqual(len(self.komut.notrlestirilen), 1)
        self.assertTrue(self.komut.notrlestirilen[0].startswith("pnl_sbl"))
        self.assertTrue(any("UPDATE res_users SET password = NULL" in s and "ir_mail_server" in s for s in self.komut.calisan_sql))
        self.assertTrue(any("gib_integrator" in s for s in self.komut.calisan_sql))
        # geçici veritabanı, birim ve klasör silindi
        self.assertEqual([k for k in self.komut.veritabanlari if k[1].startswith("pnl_sbl")], [])
        self.assertEqual(self.komut.birimler, birimler)
        self.assertEqual({p.name for p in self.ayar.odoolar.iterdir()}, odoolar)

        sonuc = self.kur("yeni", "temel")
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertTrue(self.komut.yuklenen_dokumler[-1][0] == "pnl_yeni")
        self.assertTrue(self.komut.yuklenen_dokumler[-1][1].startswith("pnl_sbl"))
        self.assertEqual(self.komut.konteynerler["pnl-yeni"], "running")
        self.assertEqual(self.s.giris_bilgisi("yeni")["kullanici"], "admin")

    def test_temizlik_dogrulanamazsa_sablon_olusmaz(self):
        self.komut.sablon_denetim = "kullanici=3\nsifre=0\nposta=0"
        sonuc = self.sablon(tur="veri", onay=True)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("etkin kullanıcı", sonuc["hata"])
        self.assertEqual(self.s.sablonlar.liste(), [])
        self.assertEqual([p.name for p in self.ayar.sablonlar.iterdir()], [])
        self.assertEqual([k for k in self.komut.veritabanlari if k[1].startswith("pnl_sbl")], [])

    def test_gecersiz_istekler(self):
        with self.assertRaises(Hata) as h:
            self.s.sablonlar.olustur("deneme", "production", {"ad": "temel", "tur": "veri"})
        self.assertIn("onaylayın", h.exception.mesaj)
        for govde in ({"ad": "x", "tur": "moduller"}, {"ad": "Temel!", "tur": "moduller"}, {"ad": "temel", "tur": "baska"}):
            with self.assertRaises(Hata):
                self.s.sablonlar.olustur("deneme", "production", govde)
        self.assertEqual(self.sablon()["durum"], "tamam")
        with self.assertRaises(Hata) as h:
            self.s.sablonlar.olustur("deneme", "production", {"ad": "temel", "tur": "moduller"})
        self.assertEqual(h.exception.kod, 409)
        with self.assertRaises(Hata) as h:
            self.s.kurulum.kur({"id": "yeni", "baslangic": "panel-sablon", "sablon": "yok-boyle"})
        self.assertEqual(h.exception.kod, 404)

    def test_sil(self):
        self.sablon()
        self.assertEqual(self.s.sablonlar.sil("temel"), {"silindi": "temel"})
        self.assertEqual(self.s.sablonlar.liste(), [])
        with self.assertRaises(Hata):
            self.s.sablonlar.sil("temel")

    def test_imaji_silinen_sablon_isaretlenir(self):
        self.sablon()
        del self.komut.imajlar[self.pr["imaj"]]
        self.assertFalse(self.s.sablonlar.liste()[0]["imaj_var"])

    def test_temizlik_sql_zamanlanmis_isleri_geri_acar(self):
        sql = temizlik_sql(["11", "12"])
        self.assertIn("UPDATE ir_cron SET active = true WHERE id IN (11,12);", sql)
        self.assertIn("database.is_neutralized", sql)
        self.assertIn("web.neutralize_banner", sql)
        self.assertNotIn("UPDATE ir_cron", temizlik_sql([]))


class ImajTesti(Temel):
    def etiket(self, imaj, seri, tur, kur=""):
        self.komut.imajlar[imaj] = "sha256:" + imaj
        self.komut.imaj_etiket[imaj] = {"vekosis.imaj": "1", "vekosis.imaj.seri": seri, "vekosis.imaj.tur": tur,
                                        "vekosis.imaj.ad": f"Odoo {seri[:2]} {tur}", "vekosis.imaj.kur": kur}

    def test_her_surum_ve_tur_icin_en_yeni_imaj(self):
        self.etiket("vekosis/odoo20:20261015-1", "20.0", "community")
        self.etiket("vekosis/odoo20:20261102-1", "20.0", "community")
        self.etiket("vekosis/odoo20e:20261102-1", "20.0", "enterprise")
        self.etiket("vekosis/odoo19:20261102-1", "19.0", "community")
        self.assertEqual([i["imaj"] for i in self.s.ortamlar.imajlar()],
                         ["vekosis/odoo20:20261102-1", "vekosis/odoo20e:20261102-1", "vekosis/odoo19:20261102-1"])

    def test_bos_kurulum_imajin_turkce_modullerini_kurar(self):
        self.komut.imaj_moduller = ["base", "web", "vekosis_web_html_lang"]
        self.etiket("vekosis/odoo20:20261102-1", "20.0", "community", "vekosis_web_html_lang,yok_boyle,../kotu")
        sonuc = self.is_sonucu(self.s.kurulum.kur({"id": "yeni", "baslangic": "bos", "imaj": "vekosis/odoo20:20261102-1"}))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(self.komut.veritabanlari[("vtest-postgres", "pnl_yeni")], {"base", "vekosis_web_html_lang"})

    def test_etiketsiz_imajda_yalniz_base(self):
        sonuc = self.is_sonucu(self.s.kurulum.kur({"id": "yeni", "baslangic": "bos", "imaj": IMAJ}))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(self.komut.veritabanlari[("vtest-postgres", "pnl_yeni")], {"base"})
