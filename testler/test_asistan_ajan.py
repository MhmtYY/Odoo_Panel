"""Ajan tarafı asistan uçları (kod okuma, salt okunur SQL, staging commit) ve açık hata metinleri."""
import subprocess
import unittest

from ajan.hata import Hata
from ajan.komut import Sonuc, hata_acikla

from .yardimci import GIT, Temel, modul


class HataAciklamaTesti(unittest.TestCase):
    def test_python_izi(self):
        cikti = ('Traceback (most recent call last):\n  File "<string>", line 5, in <module>\n'
                 "AttributeError: module 'odoo' has no attribute 'addons'")
        mesaj, ayrinti = hata_acikla(["docker", "run", "--rm", "--entrypoint", "python3", "img", "-c", "x"], Sonuc(1, cikti))
        self.assertEqual(mesaj, "Odoo imajı içindeki Python betiği hata verdi: AttributeError: module 'odoo' has no "
                                "attribute 'addons'")
        self.assertIn("$ docker run --rm", ayrinti)
        self.assertIn("Çıkış kodu: 1", ayrinti)

    def test_bilinen_neden(self):
        mesaj, _ = hata_acikla(["docker", "exec", "-i", "pg", "pg_dump"], Sonuc(1, "pg_dump: error: No space left on device"))
        self.assertTrue(mesaj.startswith("Veritabanı komutu hata verdi: Sunucuda disk dolu."), mesaj)
        mesaj, _ = hata_acikla(["git", "fetch"], Sonuc(128, "git@github.com: Permission denied (publickey)."))
        self.assertIn("GitHub deposuna erişilemedi", mesaj)
        mesaj, _ = hata_acikla(["docker", "stop", "x"], Sonuc(3, ""))
        self.assertEqual(mesaj, "Docker komutu (stop) hata verdi (çıkış kodu 3).")


class MesgulMetniTesti(Temel):
    def test_suren_is_anlatilir(self):
        self.odoo_kur()
        self.s.isler._aktif["deneme/production"] = "abcdef123456"
        self.s.isler.kaydet({"id": "abcdef123456", "tur": "yedek", "aciklama": "Yedek alma", "kullanici": "ayse",
                             "baslangic": "2026-11-10T18:28:05", "durum": "calisiyor"})
        with self.assertRaises(Hata) as h:
            self.s.yedek_al("deneme", "production", "vekosis")
        self.assertEqual(h.exception.kod, 409)
        self.assertEqual(h.exception.mesaj, "Bu ortamda süren bir iş var (Yedek alma, ayse, 18:28 başladı). Bitince tekrar deneyin.")


class KodVeSqlTesti(Temel):
    app = True

    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.commit({**modul("mod_a"), "mod_a/models/a.py": "SINIR = 1\n# installable notu\n"}, "[ADD] mod_a")
        self.commit({"mod_a/README.md": "staging\n"}, "staging dalı", dal="staging")
        self.depo_bagla(staging="staging", baglanti="app")
        self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))

    def test_kod_okuma(self):
        a = self.s.asistan
        self.assertEqual([o["ad"] for o in a.kod_listele("deneme", "production")["ogeler"]], ["depo", "ek"])
        self.assertIn("mod_a", [o["ad"] for o in a.kod_listele("deneme", "production", "depo")["ogeler"]])
        v = a.kod_oku("deneme", "production", "depo/mod_a/models/a.py")
        self.assertEqual((v["toplam_satir"], v["icerik"].splitlines()[0]), (2, "1\tSINIR = 1"))
        bulunan = a.kod_ara("deneme", "production", r"installable")["sonuc"]
        self.assertTrue(any(b["yol"] == "depo/mod_a/models/a.py" and b["satir"] == 2 for b in bulunan))
        for yol, kod in (("depo/../../ayar", 400), ("depo/mod_a/odoo.conf", 403), ("depo/.env", 403), ("yok/x.py", 404)):
            with self.assertRaises(Hata) as h:
                a.kod_oku("deneme", "production", yol)
            self.assertEqual(h.exception.kod, kod, yol)

    def test_sql_sinirlari(self):
        a = self.s.asistan
        for sorgu in ("DELETE FROM res_partner", "SELECT 1; DROP TABLE res_partner", "UPDATE x SET y = 1", ""):
            with self.assertRaises(Hata):
                a.sql_oku("deneme", "production", sorgu)
        self.assertEqual(self.komut.bul("pnl_okuyucu"), [])  # reddedilen sorgu veritabanına hiç gitmez
        v = a.sql_oku("deneme", "production", "SELECT id, name FROM res_partner WHERE name = 'a;b'")
        self.assertEqual(v["sutunlar"], ["id", "name"])
        cagri = self.komut.bul("-U pnl_okuyucu")[0]
        self.assertIn("--csv", cagri)
        # rol hazırlığı süper kullanıcıyla, sorgu okuyucu rolüyle ve salt okunur işlemde
        hazirlik = [c for c in self.komut.cagrilar if "-U" in c and c[c.index("-U") + 1] != "pnl_okuyucu"]
        self.assertTrue(hazirlik)

    def test_staging_commit(self):
        a = self.s.asistan
        for yol in (".github/workflows/x.yml", "../x.py", "setup.py", "mod_a/odoo.conf"):
            with self.assertRaises(Hata, msg=yol):
                a.staging_commit("deneme", [{"yol": yol, "icerik": "x"}], "m", "ayse", self.s.isler)
        is_kaydi = a.staging_commit("deneme", [{"yol": "mod_a/models/a.py", "icerik": "SINIR = 2\n"},
                                               {"yol": "mod_a/models/yeni.py", "icerik": "YENI = True\n"}],
                                    "[FIX] mod_a: sınır", "ayse", self.s.isler)
        sonuc = self.is_sonucu(is_kaydi)
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(sonuc["sonuc"]["dal"], "staging")
        goster = lambda yol: subprocess.run(GIT + ["--git-dir", str(self.uzak), "show", f"staging:{yol}"],  # noqa: E731
                                            capture_output=True, text=True).stdout
        self.assertEqual(goster("mod_a/models/a.py"), "SINIR = 2\n")
        self.assertEqual(goster("mod_a/models/yeni.py"), "YENI = True\n")
        mesaj = subprocess.run(GIT + ["--git-dir", str(self.uzak), "log", "-1", "--format=%B", "staging"],
                               capture_output=True, text=True).stdout
        self.assertIn("onaylayan: ayse", mesaj)
        # aynı içerik yeniden gönderilirse commit atılmaz
        tekrar = self.is_sonucu(a.staging_commit("deneme", [{"yol": "mod_a/models/a.py", "icerik": "SINIR = 2\n"}],
                                                 "m", "ayse", self.s.isler))
        self.assertEqual(tekrar["sonuc"], {"degisiklik": False})
