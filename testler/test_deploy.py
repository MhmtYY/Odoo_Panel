"""Kurulum, deploy, uyumluluk engeli, hata sonrası geri dönüş, geri alma, Python paket katmanı."""
from pathlib import Path

from ajan.hata import Hata

from .yardimci import Temel, modul


class KurulumTesti(Temel):
    def test_bos_kurulum(self):
        self.odoo_kur()
        od = self.s.odoolar.gerekli("deneme")
        o = self.s.ortamlar.gerekli("deneme", "production")
        self.assertEqual(od["tur"], "panel")
        self.assertEqual(od["seri"], "20.0")
        self.assertEqual(o["konteyner"], "pnl-deneme")
        self.assertEqual(o["db_adi"], "pnl_deneme")
        self.assertEqual(o["adres"], "https://deneme.panel.vekosis.com")
        self.assertEqual(self.komut.konteynerler["pnl-deneme"], "running")
        self.assertIn("pnl-deneme-data", self.komut.birimler)
        self.assertTrue((self.ayar.kenar_tenants / "deneme.panel.vekosis.com").exists())
        conf = Path(o["conf"]).read_text()
        self.assertIn("dbfilter = ^pnl_deneme$", conf)
        self.assertIn("addons_path = /mnt/repo,/mnt/vekosis-addons,/mnt/extra-addons", conf)
        self.assertIn("list_db = False", conf)
        giris = self.s.giris_bilgisi("deneme")
        self.assertEqual(giris["kullanici"], "admin")
        self.assertEqual(len(giris["sifre"]), 16)
        # şifreler iş günlüğüne düşmemeli
        for yol in self.ayar.isler.glob("*.log"):
            self.assertNotIn(giris["sifre"], yol.read_text(encoding="utf-8"))

    def test_ayni_ad_ve_gecersiz_ad(self):
        self.odoo_kur()
        with self.assertRaises(Hata) as h:
            self.s.kurulum.kur({"id": "deneme", "baslangic": "bos", "imaj": "vekosis/test20:20261108-1"})
        self.assertEqual(h.exception.kod, 409)
        for ad in ("x", "Deneme", "-abc", "abc-staging", "panel", "a--b"):
            with self.assertRaises(Hata):
                self.s.kurulum.kur({"id": ad, "baslangic": "bos", "imaj": "vekosis/test20:20261108-1"})

    def test_kurulum_yarida_kalirsa_geri_alinir(self):
        self.komut.saglik_hatasi = 99
        is_kaydi = self.s.kurulum.kur({"id": "bozuk", "baslangic": "bos", "imaj": "vekosis/test20:20261108-1"})
        self.assertEqual(self.is_sonucu(is_kaydi)["durum"], "hata")
        self.assertNotIn("pnl-bozuk", self.komut.konteynerler)
        self.assertNotIn("pnl-bozuk-data", self.komut.birimler)
        self.assertNotIn(("vtest-postgres", "pnl_bozuk"), self.komut.veritabanlari)
        self.assertFalse((self.ayar.odoolar / "bozuk").exists())
        self.assertFalse((self.ayar.kenar_tenants / "bozuk.panel.vekosis.com").exists())


class DeployTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.ilk = self.commit({**modul("mod_a"), **modul("mod_b")}, "[ADD] mod_a, mod_b")
        self.kurulu_yap("pnl_deneme", "mod_a", "mod_b")
        self.depo_bagla()

    def deploy(self, ortam="production", **kw):
        is_kaydi = self.s.deploylar.baslat("deneme", ortam, **kw)
        return self.is_sonucu(is_kaydi)

    def test_ilk_deploy_ve_degisen_modul(self):
        sonuc = self.deploy()
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        o = self.s.ortamlar.gerekli("deneme", "production")
        self.assertEqual(o["commit"], self.ilk)
        self.assertTrue((Path(o["kod"]) / "mod_a" / "__manifest__.py").exists())
        self.assertEqual(self.komut.konteyner_env["pnl-deneme"]["KOD"], o["kod"])
        d = self.s.deploylar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "tamam")
        self.assertEqual(d["moduller"], ["mod_a", "mod_b"])
        self.assertTrue(d["yedek"].endswith("-DEPLOY-ONCESI.tar"))
        self.assertEqual(len(self.s.yedekler.liste("deneme", "production")), 1)
        # ikinci commit yalnız mod_a'yı değiştirir -> yalnız mod_a güncellenir
        ikinci = self.commit({"mod_a/models/a.py": "x = 1\n"}, "[IMP] mod_a")
        sonuc = self.deploy()
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(self.komut.guncellenenler[-1][1], ["mod_a"])
        self.assertTrue(self.komut.guncellenenler[-1][2].endswith(ikinci))
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "production")["commit"], ikinci)

    def test_kurulu_olmayan_yeni_modul_kurulmaz(self):
        self.deploy()
        self.commit(modul("mod_c"), "[ADD] mod_c")
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "tamam")
        self.assertEqual(d["moduller"], [])
        self.assertEqual(d["yeni_moduller"], ["mod_c"])

    def test_uyumsuz_commit_deployu_durdurur(self):
        self.deploy()
        onceki_env = dict(self.komut.konteyner_env["pnl-deneme"])
        self.commit({"mod_a/__manifest__.py": modul("mod_a", surum="19.0.1.0.0")["mod_a/__manifest__.py"]},
                    "[MIG] yanlış seri")
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertEqual(d["durum"], "durdu")
        self.assertIn("19.0 serisi", d["engel"])
        self.assertEqual(self.komut.konteynerler["pnl-deneme"], "running")
        self.assertEqual(self.komut.konteyner_env["pnl-deneme"], onceki_env)
        self.assertEqual(len(self.komut.guncellenenler), 1)

    def test_enterprise_bagimliligi_ve_sozdizimi_engeli(self):
        self.commit({**modul("mod_a", depends=("base", "account_accountant")), "mod_b/models/b.py": "def x(:\n"},
                    "bozuk")
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "durdu", sonuc.get("cikti"))
        nedenler = " ".join(e["neden"] for e in d["engeller"])
        self.assertIn("Enterprise modülüne bağlı: account_accountant", nedenler)
        self.assertIn("Python sözdizimi hatası", nedenler)

    def test_guncelleme_hatasinda_veri_ve_kod_geri_doner(self):
        self.deploy()
        eski = self.s.ortamlar.gerekli("deneme", "production")
        self.commit({"mod_a/models/a.py": "x = 2\n"}, "[FIX] mod_a")
        self.komut.guncelleme_hatasi = True
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertEqual(d["durum"], "hata")
        self.assertIn("Modül güncellemesi başarısız", d["hata"])
        self.assertIn("Önceki sürüme dönüldü", d["not"])
        self.assertIn("yedekten geri yüklendi", d["not"])
        self.assertTrue(self.komut.bul("pg_restore"))
        o = self.s.ortamlar.gerekli("deneme", "production")
        self.assertEqual(o["commit"], eski["commit"])
        self.assertEqual(self.komut.konteyner_env["pnl-deneme"]["KOD"], eski["kod"])
        self.assertEqual(self.komut.konteynerler["pnl-deneme"], "running")

    def test_saglik_hatasinda_geri_donus(self):
        self.deploy()
        eski = self.s.ortamlar.gerekli("deneme", "production")
        self.commit({"README.md": "belge\n"}, "[DOC] yalnız belge")
        self.komut.saglik_hatasi = 1
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertEqual(d["moduller"], [])
        self.assertIn("Önceki sürüme dönüldü", d["not"])
        self.assertNotIn("yedekten", d["not"])  # modül güncellenmediği için veri geri yüklenmez
        self.assertEqual(self.komut.konteyner_env["pnl-deneme"]["KOD"], eski["kod"])

    def test_geri_al_kod_ve_kod_veri(self):
        self.deploy()
        ilk_kod = self.s.ortamlar.gerekli("deneme", "production")["kod"]
        self.commit({"mod_a/models/a.py": "x = 3\n"}, "[IMP] mod_a")
        self.deploy()
        sonuc = self.is_sonucu(self.s.deploylar.geri_al("deneme", "production", 2, "kod"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        d3 = self.s.deploylar.kayit_oku("deneme", "production", 3)
        self.assertEqual((d3["tetik"], d3["commit"], d3["geri_alinan"]), ("geri", self.ilk, 2))
        self.assertEqual(self.komut.guncellenenler[-1][1], ["mod_a"])
        # kod + veri: 3 numaralı geri almayı geri al (yedek + önceki kod)
        restore_once = len(self.komut.bul("pg_restore"))
        sonuc = self.is_sonucu(self.s.deploylar.geri_al("deneme", "production", 3, "kod-veri"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(len(self.komut.bul("pg_restore")), restore_once + 1)
        d4 = self.s.deploylar.kayit_oku("deneme", "production", 4)
        self.assertTrue(d4["yedek"].endswith("GERI-ALMA-ONCESI.tar"))
        self.assertNotEqual(self.s.ortamlar.gerekli("deneme", "production")["kod"], ilk_kod)
        with self.assertRaises(Hata):
            self.s.deploylar.geri_al("deneme", "production", 1, "kod")  # öncesinde commit yok

    def test_python_paket_katmani(self):
        self.commit({**modul("mod_a", python=("xlsxwriter",)), "requirements.txt": "xlsxwriter==3.2.0\n"},
                    "[ADD] xlsxwriter")
        sonuc = self.deploy()
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        o = self.s.ortamlar.gerekli("deneme", "production")
        self.assertTrue(o["imaj"].startswith("pnl/deneme:"))
        self.assertEqual(o["imaj_temel"], "vekosis/test20:20261108-1")
        self.assertTrue(self.komut.bul("docker build"))
        # aynı gereksinimle ikinci deploy imajı yeniden derlemez
        self.commit({"mod_b/models/b.py": "y = 1\n"}, "[IMP] mod_b")
        self.deploy()
        self.assertEqual(len(self.komut.bul("docker build")), 1)

    def test_python_paketi_eksikse_engel_ve_guvensiz_gereksinim(self):
        self.commit(modul("mod_a", python=("xlsxwriter",)), "paket yok")
        self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "durdu")
        self.assertIn("Python paketi imajda yok: xlsxwriter", d["engel"])
        self.commit({"requirements.txt": "git+https://example.com/x.git\n"}, "güvensiz")
        sonuc = self.deploy()
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertIn("requirements.txt satır 1", d["hata"])
        self.assertEqual(self.komut.konteynerler["pnl-deneme"], "running")

    def test_ayni_ortamda_ikinci_is_mesgul(self):
        self.s.isler._aktif["deneme/production"] = "x"
        with self.assertRaises(Hata) as h:
            self.s.deploylar.baslat("deneme", "production")
        self.assertEqual(h.exception.kod, 409)
        bekleyen1 = self.s.deploylar.baslat("deneme", "production", kuyruk=True)
        bekleyen2 = self.s.deploylar.baslat("deneme", "production", kuyruk=True)
        self.assertEqual(self.s.isler.oku(bekleyen1["id"])["durum"], "atlandi")
        self.assertEqual(self.s.isler.oku(bekleyen2["id"])["durum"], "bekliyor")
