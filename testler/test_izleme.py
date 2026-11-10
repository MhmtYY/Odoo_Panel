"""İzleme: istek satırlarının ayrıştırılması, dakikalık ölçüm ve özet."""
import time
import unittest
from datetime import datetime, timedelta

from ajan import izleme

from .yardimci import Temel

# Odoo 19+ kendi HTTP sunucusu: tarih boşluklu, yolun sonunda "#model.metot", en sonda imleç kipi
ODOO20 = ('2026-11-10 18:27:01,123 7 INFO musteri odoo.http.server_log: 172.19.0.5 a1b2c3 - '
          '[Tue, 10 Nov 2026 18:27:01 GMT] "POST /json/2/res.partner/search_read#res.partner.search_read HTTP/1.1" '
          '200 1234 12 0.040 0.060 rw')
# Odoo 16-18 werkzeug satırı
ODOO17 = ('2026-11-10 18:27:02,000 7 INFO musteri werkzeug: 172.19.0.5 - - [10/Nov/2026 18:27:02] '
          '"POST /web/dataset/call_kw/account.move/web_read_group HTTP/1.1" 200 - 30 0.300 0.900')
HATA = ('2026-11-10 18:27:03,000 7 INFO musteri werkzeug: 1.2.3.4 - - [10/Nov/2026 18:27:03] '
        '"GET /my/orders/42?access_token=x HTTP/1.1" 500 - 3 0.001 0.010')
STATIK = '... werkzeug: x - - [10/Nov/2026 18:27:04] "GET /web/assets/1/web.assets_web.min.js HTTP/1.1" 200 - 0 0.000 0.002'
UZUN = '... werkzeug: x - - [10/Nov/2026 18:27:05] "GET /websocket HTTP/1.1" 101 - 1 0.001 50.000'


class IstekAyristirmaTesti(unittest.TestCase):
    def test_satirlar(self):
        sayi, hata, sureler, uclar = izleme.istekleri_ozetle([ODOO20, ODOO17, HATA, STATIK, UZUN, "alakasız satır"])
        self.assertEqual((sayi, hata), (3, 1))
        self.assertEqual(sorted(sureler), [11, 100, 1200])
        self.assertEqual(uclar["res.partner.search_read"], [1, 100, 100])
        self.assertEqual(uclar["account.move.web_read_group"], [1, 1200, 1200])
        self.assertEqual(uclar["/my/orders/:id"], [1, 11, 11])

    def test_sure_bilgisi_olmayan_satir(self):
        satir = '... werkzeug: x - - [10/Nov/2026 18:27:02] "GET /odoo HTTP/1.1" 200 -'
        self.assertEqual(izleme.istekleri_ozetle([satir])[:3], (1, 0, []))

    def test_yuzdelik(self):
        self.assertEqual(izleme.yuzdelik(list(range(1, 101)), 0.95), 95)
        self.assertIsNone(izleme.yuzdelik([], 0.95))


class IzlemeTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.komut.istek_satirlari = [ODOO20, ODOO17, HATA, STATIK]
        self.s.izleme.saglik_denetle = lambda adres: (True, 12)

    def test_olcum_ve_ozet(self):
        simdi = int(time.time())
        for i in range(5):
            self.s.izleme.ornekle(simdi - (4 - i) * 60)
        v = self.s.izleme.ozet("deneme", "production", 1)
        self.assertEqual(v["olcum_sayisi"], 5)
        son = v["son"]
        self.assertEqual((son["durum"], son["cpu"], son["bellek"], son["saglik"], son["saglik_ms"]),
                         ("running", 1.5, 512, 1, 12))
        self.assertEqual((son["istek"], son["hata5xx"], son["p95"], son["surec"], son["db_baglanti"]),
                         (3.0, 1, 1200, 5, 3))
        self.assertEqual(v["db_boyut"], 104857600)
        self.assertTrue(v["seriler"]["cpu"] and v["seriler"]["istek"] and v["seriler"]["p95"])
        self.assertEqual(v["hata_orani_24s"], 33.33)
        self.assertEqual(v["yavas"][0]["uc"], "account.move.web_read_group")
        self.assertEqual(v["erisilebilirlik_30g"], 100.0)
        self.assertEqual(len(v["gunler"]), 30)
        self.assertEqual([c["ad"] for c in v["cronlar"]], ["Posta kuyruğu", "Kur güncelleme"])
        self.assertTrue(v["istek_kaydi"])
        # docker logs yalnız son ölçümden bu yana okunur
        sinceler = [c[c.index("--since") + 1] for c in self.komut.bul("docker logs --since")]
        self.assertEqual(sinceler[1:], [str(simdi - (4 - i) * 60) for i in range(4)])

    def test_kapali_ortam_erisilebilirligi_dusurur(self):
        simdi = int(time.time())
        self.s.izleme.ornekle(simdi - 60)
        self.komut.konteynerler["pnl-deneme"] = "exited"
        self.s.izleme.ornekle(simdi)
        v = self.s.izleme.ozet("deneme", "production", 1)
        self.assertEqual(v["son"]["durum"], "exited")
        self.assertEqual(v["son"]["saglik"], 0)
        self.assertEqual(v["erisilebilirlik_30g"], 50.0)

    def test_eski_olcumler_silinir(self):
        dizin = self.ayar.kok / "izleme" / "deneme" / "production"
        dizin.mkdir(parents=True)
        eski = dizin / f"{(datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')}.jsonl"
        eski.write_text("{}\n")
        self.s.izleme.ornekle()
        self.assertFalse(eski.exists())

    def test_gecersiz_aralik_24_saate_doner(self):
        self.s.izleme.ornekle()
        self.assertEqual(self.s.izleme.ozet("deneme", "production", "999")["aralik_saat"], 24)
