"""Otomatik yedek planı: genel varsayılan + platform başına, saatlik tur, gün bazlı saklama."""
import unittest
from datetime import datetime, timedelta

from ajan.hata import Hata
from ajan.yedek_plani import VARSAYILAN, plan_denetle, sonraki, zamani_geldi

from .yardimci import Temel

GUNLUK = {"periyot_saat": 24, "saat": 4, "saklama_gun": 7}


class ZamanlamaTesti(unittest.TestCase):
    def an(self, gun, saat, dakika=20):
        return datetime(2026, 11, gun, saat, dakika)

    def test_gunluk(self):
        self.assertTrue(zamani_geldi(GUNLUK, None, self.an(12, 4)))  # ilk yedek: ilk 04:20
        self.assertFalse(zamani_geldi(GUNLUK, None, self.an(12, 5)))
        son = self.an(12, 4, 22)
        self.assertFalse(zamani_geldi(GUNLUK, son, self.an(12, 5)))
        self.assertFalse(zamani_geldi(GUNLUK, son, self.an(13, 3)))
        self.assertTrue(zamani_geldi(GUNLUK, son, self.an(13, 4, 19)))  # gecikmeli yedekten sonra da yerinde
        # sunucu kapalıydı: yedek saati beklenmez
        self.assertTrue(zamani_geldi(GUNLUK, son, self.an(13, 7)))

    def test_alti_saatlik_ve_haftalik(self):
        alti = {"periyot_saat": 6, "saat": 4, "saklama_gun": 3}
        self.assertEqual([h for h in range(24) if zamani_geldi(alti, None, self.an(12, h))], [4, 10, 16, 22])
        self.assertTrue(zamani_geldi(alti, self.an(12, 10, 21), self.an(12, 16)))
        self.assertFalse(zamani_geldi(alti, self.an(12, 10, 21), self.an(12, 13)))
        hafta = {"periyot_saat": 168, "saat": 2, "saklama_gun": 60}
        son = self.an(5, 2)
        self.assertFalse(zamani_geldi(hafta, son, self.an(11, 2)))
        self.assertTrue(zamani_geldi(hafta, son, self.an(12, 2)))

    def test_kapali(self):
        kapali = {**GUNLUK, "periyot_saat": 0}
        self.assertFalse(zamani_geldi(kapali, None, self.an(12, 4)))
        self.assertIsNone(sonraki(kapali, None, self.an(12, 4)))

    def test_sonraki(self):
        self.assertEqual(sonraki(GUNLUK, self.an(12, 4, 22), self.an(12, 9, 5)), self.an(13, 4))
        iki = {**GUNLUK, "periyot_saat": 48}
        self.assertEqual(sonraki(iki, self.an(12, 4, 22), self.an(12, 9, 5)), self.an(14, 4))

    def test_denetim(self):
        self.assertEqual(plan_denetle({}), VARSAYILAN)
        self.assertEqual(plan_denetle({"periyot_saat": "12", "saat": "23", "saklama_gun": "30"}),
                         {"periyot_saat": 12, "saat": 23, "saklama_gun": 30})
        for kotu in ({"periyot_saat": 5}, {"saat": 24}, {"saklama_gun": 0}, {"saklama_gun": 400}, {"saat": "x"}):
            with self.assertRaises(Hata):
                plan_denetle(kotu)


class PlanTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.odoo_kur("tekstil")
        self.p = self.s.yedek_plani

    def yedek_dosyasi(self, odoo_id, an, etiket="OTOMATIK"):
        dizin = self.s.yedekler.dizin(odoo_id, "production")
        dizin.mkdir(parents=True, exist_ok=True)
        ad = f"{odoo_id}-production-{an:%Y%m%d-%H%M%S}-{etiket}.tar"
        (dizin / ad).write_bytes(b"x")
        return ad

    def test_genel_ve_platform_plani(self):
        self.assertEqual(self.p.genel(), VARSAYILAN)
        self.p.genel_yaz({"periyot_saat": 12, "saat": 2, "saklama_gun": 14})
        self.assertEqual(self.p.platform("deneme")["gecerli"], {"periyot_saat": 12, "saat": 2, "saklama_gun": 14})
        bilgi = self.p.platform_yaz("deneme", {"ozel": {"periyot_saat": 24, "saat": 3, "saklama_gun": 30}})
        self.assertEqual((bilgi["gecerli"]["saklama_gun"], bilgi["ozel"]["saat"]), (30, 3))
        # genel değişince özel planlı platform etkilenmez, diğeri etkilenir
        self.p.genel_yaz({"periyot_saat": 6, "saat": 0, "saklama_gun": 2})
        self.assertEqual(self.p.platform("deneme")["gecerli"]["saklama_gun"], 30)
        self.assertEqual(self.p.platform("tekstil")["gecerli"]["periyot_saat"], 6)
        ozet = {x["id"]: x for x in self.p.ozet()["platformlar"]}
        self.assertEqual((ozet["deneme"]["ozel"], ozet["tekstil"]["ozel"]), (True, False))
        # genele dönüş
        self.assertIsNone(self.p.platform_yaz("deneme", {"ozel": None})["ozel"])
        self.assertNotIn("yedek_plani", self.s.odoolar.gerekli("deneme"))
        with self.assertRaises(Hata):
            self.p.platform_yaz("deneme", {"ozel": {"periyot_saat": 7}})

    def test_saatlik_tur_yalniz_zamani_geleni_yedekler(self):
        self.p.platform_yaz("tekstil", {"ozel": {"periyot_saat": 0, "saat": 4, "saklama_gun": 7}})
        an = datetime.now().replace(hour=4, minute=20, second=0, microsecond=0)
        sonuc = {(x["odoo"], x["ortam"]): x for x in self.p.tur(an)}
        self.assertEqual(sonuc[("deneme", "production")]["durum"], "alindi")
        self.assertEqual(sonuc[("tekstil", "production")]["durum"], "kapali")
        yedekler = self.s.yedekler.liste("deneme", "production")
        self.assertEqual([y["etiket"] for y in yedekler], ["OTOMATIK"])
        self.assertEqual(self.s.yedekler.liste("tekstil", "production"), [])
        # aynı saatte ikinci tur yeni yedek almaz
        self.assertEqual({x["durum"] for x in self.p.tur(an + timedelta(minutes=30)) if x["odoo"] == "deneme"}, {"bekliyor"})
        self.assertEqual(len(self.s.yedekler.liste("deneme", "production")), 1)

    def test_saklama_suresi_gun_bazli_en_yenisi_kalir(self):
        # yalnız silme kuralı sınanır: yedek kapalı (kapalıyken de saklama süresi uygulanır)
        self.p.genel_yaz({"periyot_saat": 0, "saat": 4, "saklama_gun": 7})
        an = datetime.now().replace(hour=9, minute=20, second=0, microsecond=0)
        eski = [self.yedek_dosyasi("deneme", an - timedelta(days=g)) for g in (10, 9, 8)]
        gece = self.yedek_dosyasi("deneme", an - timedelta(days=12), "GECE")
        yeni = self.yedek_dosyasi("deneme", an - timedelta(days=2))
        elle = self.yedek_dosyasi("deneme", an - timedelta(days=30), "ELLE")
        self.p.tur(an)
        kalan = {y["dosya"] for y in self.s.yedekler.liste("deneme", "production")}
        self.assertEqual(kalan, {yeni, elle})
        self.assertTrue(set(eski + [gece]).isdisjoint(kalan))
        # hepsi saklama süresini aştıysa en yenisi yine kalır
        a = self.yedek_dosyasi("tekstil", an - timedelta(days=40))
        self.yedek_dosyasi("tekstil", an - timedelta(days=50))
        self.p.tur(an)
        self.assertEqual({y["dosya"] for y in self.s.yedekler.liste("tekstil", "production")}, {a})

    def test_platform_ozetinde_son_ve_sonraki(self):
        an = datetime.now().replace(hour=9, minute=5, second=0, microsecond=0)
        self.yedek_dosyasi("deneme", an.replace(hour=4, minute=22))
        bilgi = self.p.platform("deneme", an)["ortamlar"]["production"]
        self.assertTrue(bilgi["son"].endswith("04:22:00"))
        self.assertEqual(bilgi["sonraki"], (an + timedelta(days=1)).replace(hour=4, minute=20).isoformat(timespec="minutes"))
