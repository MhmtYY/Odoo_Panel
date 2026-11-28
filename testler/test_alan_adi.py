"""Platformun kendi alan adı (ajan/alan_adi.py): kayıt, çakışma ve DNS denetimi, uygulama, geri alma, kaldırma."""
import unittest
from pathlib import Path

from ajan.alan_adi import adres_sql, alan_normallestir, caddy_siteleri, joker_eslesir, joker_hedef
from ajan.ayar import ortamdan
from ajan.hata import Hata
from ajan.servis import Servis
from panel.yetki import istek_bul, yetkili

from .sahte import SahteKomut
from .yardimci import Temel

KOK = Path(__file__).resolve().parents[1]
ALAN = "deneme.test.vekosis.com"
PANEL = "deneme.panel.vekosis.com"
IP = "89.167.114.61"

KENAR_CADDYFILE = """{
    on_demand_tls {
        ask http://localhost:5555/
    }
}

:5555 {
    @izin file /etc/caddy/tenants/{query.domain}
    respond @izin 200
    respond 404
}

erp.vekosis.com {
    reverse_proxy /websocket* erp20-odoo:8072
    reverse_proxy erp20-odoo:8069
}

test.vekosis.com {
    reverse_proxy vtest-panel:8080
}

*.test.vekosis.com {
    tls {
        on_demand
    }
    reverse_proxy /websocket* odoo-{labels.3}:8072
    reverse_proxy odoo-{labels.3}:8069 {
        request_buffers 16MB
    }
}

import /etc/caddy/panel.caddy
"""


class CaddyKomut(SahteKomut):
    """Sahte komutlara curl (url -> çıktı) ve başarısız caddy validate/reload eklenir."""

    def __init__(self):
        super().__init__()
        self.curl = {}
        self.caddy_hata = []  # sıradaki "validate" / "reload" çağrıları başarısız

    def calistir(self, args, **kw):
        args = [str(a) for a in args]
        log, kontrol = kw.get("log"), kw.get("kontrol", True)
        if args[0] == "curl":
            self.cagrilar.append(args)
            return self._sonuc(0, self.curl.get(args[-1], "000"), log, kontrol, args)
        if args[:2] == ["docker", "exec"] and args[3:4] == ["caddy"] and args[4] in self.caddy_hata:
            self.caddy_hata.remove(args[4])
            self.cagrilar.append(args)
            return self._sonuc(1, "Error: adapting config: ambiguous site definition", log, kontrol, args)
        return super().calistir(args, **kw)


class YardimciIslevTesti(unittest.TestCase):
    def test_alan_normallestir(self):
        self.assertEqual(alan_normallestir(" HTTPS://Decros.Test.Vekosis.com/web "), "decros.test.vekosis.com")
        self.assertEqual(alan_normallestir("erp.ornekfirma.com.tr."), "erp.ornekfirma.com.tr")
        idna = alan_normallestir("Çiçek.com.tr")
        self.assertTrue(idna.startswith("xn--") and idna.endswith(".com.tr"), idna)
        for bozuk in ("", "localhost", "a..b.com", "x.com:8443", "kim@x.com", "-a.com", "a_b.com", "x.123"):
            with self.assertRaises(Hata, msg=bozuk):
                alan_normallestir(bozuk)

    def test_caddy_siteleri_ve_joker(self):
        siteler = {tuple(s["adresler"]): s["hedef"] for s in caddy_siteleri(KENAR_CADDYFILE)}
        self.assertEqual(siteler, {("erp.vekosis.com",): "erp20-odoo:8069", ("test.vekosis.com",): "vtest-panel:8080",
                                   ("*.test.vekosis.com",): "odoo-{labels.3}:8069"})
        self.assertTrue(joker_eslesir("*.test.vekosis.com", "musteri.test.vekosis.com"))
        self.assertFalse(joker_eslesir("*.test.vekosis.com", "test.vekosis.com"))
        self.assertFalse(joker_eslesir("*.test.vekosis.com", "a.b.test.vekosis.com"))
        self.assertEqual(joker_hedef("odoo-{labels.3}:8069", "musteri.test.vekosis.com"), "odoo-musteri")
        self.assertIsNone(joker_hedef("{http.request.host}:8069", "musteri.test.vekosis.com"))

    def test_adres_sql(self):
        sql = adres_sql(ALAN, [PANEL])
        self.assertIn(f"VALUES ('web.base.url', 'https://{ALAN}'", sql)
        self.assertIn(f"WHERE domain IN ('{PANEL}', 'http://{PANEL}', 'https://{PANEL}')", sql)
        with self.assertRaises(Hata):
            adres_sql("x'; DROP TABLE res_users; --", [PANEL])

    def test_ortam_degiskenleri_ve_yetki(self):
        a = ortamdan({"PANEL_CADDY_ALANLAR": "/opt/edge/etc/panel-alanlar", "PANEL_CADDY": "edge-caddy"})
        self.assertEqual((str(a.caddy_alanlar).replace("\\", "/"), a.caddy_konteyner),
                         ("/opt/edge/etc/panel-alanlar", "edge-caddy"))
        self.assertIsNone(ortamdan({"PANEL_CADDY_ALANLAR": ""}).caddy_alanlar)  # Verisfa profili: kapalı
        self.assertIsNone(ortamdan({}).caddy_alanlar)
        self.assertEqual(istek_bul("POST", "odoolar/decros/alan-adi/uygula")[1:], ("alanAdi", "odoo"))
        self.assertEqual(istek_bul("GET", "odoolar/decros/alan-adi")[1:], ("izle", "odoo"))
        self.assertTrue(yetkili("yonetici", "alanAdi"))
        self.assertFalse(yetkili("kullanici", "alanAdi"))

    def test_sunucu_dosyalari_klasoru_ice_aktarir(self):
        caddy = (KOK / "sunucu" / "Caddyfile.panel").read_text(encoding="utf-8")
        self.assertIn("import /etc/caddy/panel-alanlar/*.caddy", caddy)
        kur = (KOK / "sunucu" / "kur.sh").read_text(encoding="utf-8")
        self.assertIn("PANEL_CADDY_ALANLAR=$KENAR/etc/panel-alanlar", kur)
        self.assertIn('mkdir -p "$KENAR/etc/panel-alanlar"', kur)


class AlanAdiTesti(Temel):
    def setUp(self):
        super().setUp()
        self.komut = CaddyKomut()
        self.s = Servis(self.ayar, komut=self.komut, http=self.http, senkron=True)
        etc = self.ayar.kenar_tenants.parent
        self.ayar.caddy_alanlar = etc / "panel-alanlar"
        etc.mkdir(parents=True, exist_ok=True)
        (etc / "Caddyfile").write_text(KENAR_CADDYFILE, encoding="utf-8")
        (etc / "panel.caddy").write_text((KOK / "sunucu" / "Caddyfile.panel").read_text(encoding="utf-8"),
                                         encoding="utf-8")
        self.dns = {(PANEL, 4): {IP}, (ALAN, 4): {IP}}
        self.s.alan_adlari.cozumle = lambda ad, surum: set(self.dns.get((ad, surum), set()))
        self.s.alan_adlari.bekleme = 0
        self.odoo_kur()
        self.komut.curl.update({f"https://{ALAN}/web/login": "200", f"https://{PANEL}/": f"302 https://{ALAN}/",
                                f"https://{PANEL}/web/login": "200"})

    # -- yardımcılar
    def kural(self):
        yol = self.ayar.caddy_alanlar / "deneme.caddy"
        return yol.read_text(encoding="utf-8") if yol.exists() else None

    def izin(self, ad):
        return (self.ayar.kenar_tenants / ad).exists()

    def pr(self):
        return self.s.ortamlar.gerekli("deneme", "production")

    def caddy_cagrilari(self, islem):
        return [c for c in self.komut.cagrilar if c[:2] == ["docker", "exec"] and c[3:5] == ["caddy", islem]]

    def uygula(self):
        self.s.alan_adlari.kaydet("deneme", {"alan": ALAN}, "tester")
        return self.is_sonucu(self.s.alan_adlari.uygula("deneme", "tester"))

    # -- kayıt ve denetimler
    def test_kayit_ve_rapor(self):
        v = self.s.alan_adlari.kaydet("deneme", {"alan": "Deneme.Test.Vekosis.com"}, "tester")
        self.assertEqual((v["kayit"]["alan"], v["kayit"]["durum"]), (ALAN, "bekliyor"))
        self.assertTrue(v["rapor"]["hazir"], v["rapor"])
        self.assertEqual(v["panel_adresi"], PANEL)
        self.assertEqual(v["ip"], IP)
        # joker kuralın altında, odoo-deneme yok: engel değil uyarı
        self.assertTrue(any("*.test.vekosis.com" in u for u in v["rapor"]["uyarilar"]))
        # kaydetmek hiçbir şeye dokunmaz
        self.assertIsNone(self.kural())
        self.assertFalse(self.izin(ALAN))
        self.assertEqual(self.pr()["adres"], f"https://{PANEL}")

    def test_dns_hazir_degilse_kaydedilir_ama_uygulanmaz(self):
        self.dns[(ALAN, 4)] = {"1.2.3.4"}
        self.dns[(ALAN, 6)] = {"2001:db8::1"}
        v = self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        self.assertFalse(v["rapor"]["hazir"])
        self.assertEqual(len(v["rapor"]["engeller"]), 2)
        self.assertIn("1.2.3.4", v["rapor"]["engeller"][0])
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.uygula("deneme")
        self.assertEqual(h.exception.kod, 409)
        del self.dns[(ALAN, 4)]
        self.assertIn("DNS'te görünmüyor", self.s.alan_adlari.durum("deneme")["rapor"]["engeller"][0])

    def test_cakisan_adlar_reddedilir(self):
        self.komut.konteynerler["odoo-musteri"] = "running"  # test platformundaki ortam
        for alan, parca in ((PANEL, "panelin kendi"), ("baska.panel.vekosis.com", "panelin kendi"),
                            ("erp.vekosis.com", "erp20-odoo"), ("musteri.test.vekosis.com", "odoo-musteri")):
            with self.assertRaises(Hata, msg=alan) as h:
                self.s.alan_adlari.kaydet("deneme", {"alan": alan})
            self.assertIn(parca, h.exception.mesaj)
        self.assertNotIn("alan_adi", self.pr())

    def test_baska_platformdaki_ad_reddedilir(self):
        self.odoo_kur("ikinci")
        self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.kaydet("ikinci", {"alan": ALAN})
        self.assertIn("deneme", h.exception.mesaj)

    def test_ozellik_kapaliysa(self):
        self.ayar.caddy_alanlar = None
        self.assertFalse(self.s.alan_adlari.durum("deneme")["acik"])
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        self.assertIn("kur.sh", h.exception.mesaj)

    def test_import_satiri_yoksa_uygulanmaz(self):
        self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        (self.ayar.kenar_tenants.parent / "panel.caddy").write_text("# eski panel.caddy\n", encoding="utf-8")
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.uygula("deneme")
        self.assertIn("import", h.exception.mesaj)

    def test_bagli_kurulumda_yok(self):
        od = self.s.odoolar.gerekli("deneme")
        od["tur"] = "bagli"
        self.s.odoolar.yaz(od)
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.durum("deneme")
        self.assertEqual(h.exception.kod, 400)

    # -- uygulama
    def test_uygula(self):
        sonuc = self.uygula()
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("hata") or sonuc.get("cikti"))
        kural = self.kural()
        self.assertIn(f"{ALAN} {{", kural)
        self.assertIn("reverse_proxy pnl-deneme:8069", kural)
        self.assertIn("reverse_proxy /websocket* pnl-deneme:8072", kural)
        self.assertIn(f"{PANEL} {{", kural)
        self.assertIn(f"redir https://{ALAN}{{uri}} temporary", kural)
        self.assertTrue(self.izin(ALAN))
        self.assertTrue(self.izin(PANEL))
        # önce yalnız alan adı, sonra yönlendirme: iki kez doğrula + yükle
        self.assertEqual((len(self.caddy_cagrilari("validate")), len(self.caddy_cagrilari("reload"))), (2, 2))
        self.assertTrue(any(f"'web.base.url', 'https://{ALAN}'" in s for s in self.komut.calisan_sql))
        self.assertTrue(self.komut.bul("docker restart --time 30 pnl-deneme"))
        pr = self.pr()
        self.assertEqual(pr["adres"], f"https://{ALAN}")
        self.assertEqual((pr["alan_adi"]["durum"], pr["alan_adi"]["kullanici"]), ("etkin", "tester"))
        self.assertEqual(self.s.giris_bilgisi("deneme")["adres"], f"https://{ALAN}")
        self.assertEqual(self.s.odoo_ozeti(self.s.odoolar.gerekli("deneme"))["ortamlar"]["production"]["adres"],
                         f"https://{ALAN}")
        # uygulanmış ad başka adla değiştirilemez; önce kaldırılmalı
        with self.assertRaises(Hata):
            self.s.alan_adlari.kaydet("deneme", {"alan": "baska.test.vekosis.com"})
        # staging panel adresinde kalır
        self.is_sonucu(self.s.staging.olustur("deneme"))
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "staging")["adres"], "https://deneme-staging.panel.vekosis.com")

    def test_caddy_reddederse_geri_alinir(self):
        self.komut.caddy_hata.append("validate")
        sonuc = self.uygula()
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("Caddy yeni kuralı kabul etmedi", sonuc["hata"])
        self.assertIsNone(self.kural())
        self.assertFalse(self.izin(ALAN))
        self.assertTrue(self.izin(PANEL))
        self.assertFalse(any("web.base.url" in s for s in self.komut.calisan_sql))
        pr = self.pr()
        self.assertEqual((pr["adres"], pr["alan_adi"]["durum"]), (f"https://{PANEL}", "bekliyor"))

    def test_son_denetim_gecmezse_odoo_adresi_de_geri_alinir(self):
        self.komut.curl[f"https://{PANEL}/"] = "200"  # yönlendirme görünmüyor
        sonuc = self.uygula()
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("Son denetim geçmedi", sonuc["hata"])
        self.assertIsNone(self.kural())
        self.assertFalse(self.izin(ALAN))
        # sahte veritabanında web.base.url boş: geri almada satır silinir, web sitesi panel adresine döner
        self.assertTrue(any("DELETE FROM ir_config_parameter WHERE key = 'web.base.url'" in s
                            and f"SET domain = 'https://{PANEL}'" in s for s in self.komut.calisan_sql))
        self.assertEqual(len(self.komut.bul("docker restart --time 30 pnl-deneme")), 2)
        self.assertEqual(self.pr()["adres"], f"https://{PANEL}")

    def test_sertifika_alinamazsa(self):
        self.komut.curl[f"https://{ALAN}/web/login"] = "000"
        sonuc = self.uygula()
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("sertifika alınamadı", sonuc["hata"])
        self.assertIsNone(self.kural())
        self.assertFalse(any("web.base.url" in s for s in self.komut.calisan_sql))

    def test_durdurulmus_platformda_uygulanmaz(self):
        self.komut.konteynerler["pnl-deneme"] = "exited"
        self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        with self.assertRaises(Hata) as h:
            self.s.alan_adlari.uygula("deneme")
        self.assertIn("başlatın", h.exception.mesaj)

    # -- kaldırma, silme, geri yükleme
    def test_uygulanmamis_kayit_hemen_silinir(self):
        self.s.alan_adlari.kaydet("deneme", {"alan": ALAN})
        self.assertEqual(self.s.alan_adlari.kaldir("deneme"), {"silindi": True})
        self.assertNotIn("alan_adi", self.pr())

    def test_kaldir(self):
        self.uygula()
        self.komut.calisan_sql.clear()
        sonuc = self.is_sonucu(self.s.alan_adlari.kaldir("deneme", "tester"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("hata") or sonuc.get("cikti"))
        self.assertIsNone(self.kural())
        self.assertFalse(self.izin(ALAN))
        self.assertTrue(self.izin(PANEL))
        self.assertTrue(any(f"'web.base.url', 'https://{PANEL}'" in s and f"'https://{ALAN}'" in s
                            for s in self.komut.calisan_sql))
        pr = self.pr()
        self.assertEqual(pr["adres"], f"https://{PANEL}")
        self.assertNotIn("alan_adi", pr)

    def test_kaldirirken_joker_sahibi_varsa_izin_kalir(self):
        self.uygula()
        self.komut.konteynerler["odoo-deneme"] = "running"  # sonradan test platformunda aynı adla ortam açıldı
        self.is_sonucu(self.s.alan_adlari.kaldir("deneme"))
        self.assertTrue(self.izin(ALAN))

    def test_platform_silinince_kural_ve_izin_kalkar(self):
        self.uygula()
        sonuc = self.is_sonucu(self.s.kurulum.sil("deneme", ALAN, self.s.staging, self.s.yedekler, "tester"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("hata") or sonuc.get("cikti"))
        self.assertIsNone(self.kural())
        self.assertFalse(self.izin(ALAN))

    def test_geri_yuklemede_odoo_adresi_korunur(self):
        self.uygula()
        self.is_sonucu(self.s.yedek_al("deneme", "production"))
        dosya = self.s.yedekler.liste("deneme", "production")[0]["dosya"]
        self.komut.calisan_sql.clear()
        with self.assertRaises(Hata):  # onay artık alan adı
            self.s.geri_yukle("deneme", "production", dosya, PANEL)
        sonuc = self.is_sonucu(self.s.geri_yukle("deneme", "production", dosya, ALAN))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("hata") or sonuc.get("cikti"))
        self.assertTrue(any(f"'web.base.url', 'https://{ALAN}'" in s for s in self.komut.calisan_sql))


if __name__ == "__main__":
    unittest.main()
