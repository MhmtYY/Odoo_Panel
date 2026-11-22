"""Ortam provası (ajan/prova.py), muhasebe değişmezleri (ajan/degismez.py) ve deploy kapısı."""
from ajan import degismez, duman
from ajan.hata import Hata

from .yardimci import Temel, modul


class DegismezBirimTesti(Temel):
    def test_karsilastir_ve_beklenen_farklar(self):
        once = {"yevmiye.1": "10;100;100;0;0;1", "mizan.1": "0.00", "ebelge.account_move.gib_state.sent": "4"}
        sonra = {"yevmiye.1": "10;100;100;0;0;1", "mizan.1": "0.00", "ebelge.account_move.gib_state.sent": "3",
                 "ebelge.account_move.gib_state.error": "1"}
        sonuc = degismez.karsilastir(once, sonra)
        self.assertFalse(sonuc["gecti"])
        self.assertEqual([f["anahtar"] for f in sonuc["farklar"]],
                         ["ebelge.account_move.gib_state.error", "ebelge.account_move.gib_state.sent"])
        not_metni = ("# Yayın\n\n## Beklenen veri değişiklikleri\n\n- ebelge.account_move.gib_state: göç durumu düzeltir\n"
                     "\n## Kapı kayıtları\n\n- gib_invoice: tamam\n")
        izinli = degismez.beklenen_farklar(not_metni)
        self.assertEqual(izinli, ["ebelge.account_move.gib_state"])
        sonuc = degismez.karsilastir(once, sonra, izinli)
        self.assertTrue(sonuc["gecti"])
        self.assertEqual(len(sonuc["izinli_farklar"]), 2)

    def test_duman_karsilastir_ve_oge_adlari(self):
        self.assertEqual(duman._oge("Invoice/cac:TaxTotal[1]/cbc:TaxAmount[2]/@currencyID"), "TaxAmount@currencyID")
        self.assertEqual(duman._oge("Invoice/cac:PostalAddress[1]/cbc:BuildingNumber[1]"), "BuildingNumber")
        notu = "## Beklenen belge değişiklikleri\n- BuildingNumber: kalktı\n- `cbc:StreetName`: birleşti\n## Başka\n- X: y\n"
        self.assertEqual(duman.beklenen_belge(notu), ["BuildingNumber", "StreetName"])
        once = {"ubl": {"1": {"yaprak": {"Invoice/a:B[1]/cbc:BuildingNumber[1]": "x", "Invoice/a:B[1]/cbc:StreetName[1]": "y"}},
                        "2": {"hata": "UserError: VKN yok"}},
                "duman": {"satis": {"toplam": 1}, "kur_degerleme": {"hata": "UserError: kur yok"}}}
        sonra = {"ubl": {"1": {"yaprak": {"Invoice/a:B[1]/cbc:StreetName[1]": "z"}},
                         "2": {"hata": "UserError: VKN yok"}},
                 "duman": {"satis": {"toplam": 1}, "kur_degerleme": {"hata": "UserError: kur yok"}}}
        sonuc = duman.karsilastir(once, sonra, duman.beklenen_belge(notu))
        self.assertTrue(sonuc["gecti"])  # aynı hata eşit; değişen öğeler beklenen
        self.assertEqual(sonuc["duman"]["senaryolar"], {"kur_degerleme": "ayni-hata", "satis": "ayni"})
        sonra["ubl"]["2"] = {"yaprak": {}}
        sonuc = duman.karsilastir(once, sonra, ["BuildingNumber", "StreetName"])
        self.assertFalse(sonuc["gecti"])
        self.assertEqual(sonuc["belge"]["hata_farki"][0]["once"], "UserError: VKN yok")
        betik = duman.betik("2026-11-22", 5, "")
        self.assertIn('BUGUN = datetime.date.fromisoformat("2026-11-22")', betik)
        self.assertIn('print("VEKOSIS_DUMAN=" + json.dumps', betik)
        compile(betik, "duman_betigi", "exec")  # sözdizimi

    def test_olcum_sql_yalniz_var_olan_kolonlar(self):
        sql = degismez.olcum_sql(["account_move.company_id", "account_move.move_type", "account_move.state",
                                  "account_move.gib_state", "account_move.review_state", "gib_belge.state",
                                  "gib_integrator.state"])
        self.assertIn("'fis.'", sql)
        self.assertNotIn("account_move_line", sql)  # satır tablosu yoksa yevmiye denetimi yok
        self.assertIn("ebelge.account_move.gib_state", sql)
        self.assertNotIn("review_state", sql)  # Odoo'nun kendi alanı e-Belge sayılmaz
        self.assertIn("ebelge.gib_belge.state", sql)
        self.assertNotIn("gib_integrator", sql)  # nötrleştirme değiştirir


class ProvaTesti(Temel):
    def setUp(self):
        super().setUp()
        self.odoo_kur()
        self.ilk = self.commit({**modul("mod_a"), **modul("mod_b")}, "[ADD] mod_a, mod_b")
        self.kurulu_yap("pnl_deneme", "mod_a", "mod_b")
        self.depo_bagla()
        sonuc = self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))

    def prova(self, **kw):
        return self.is_sonucu(self.s.provalar.baslat("deneme", "production", **kw))

    def test_prova_gecer_ve_gecici_veritabani_silinir(self):
        # deploy öncesi yedek eski commit'te (ilk deploy'dan önce); şimdiki halin yedeği provada kullanılır
        self.is_sonucu(self.s.yedek_al("deneme", "production"))
        ikinci = self.commit({"mod_a/models/a.py": "x = 1\n"}, "[IMP] mod_a")
        sonuc = self.prova()
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "gecti")
        self.assertEqual((d["commit"], d["taban_commit"], d["moduller"]), (ikinci, self.ilk, ["mod_a"]))
        self.assertEqual(d["veri"]["tur"], "yedek")  # 24 saatten yeni ve ortamın şimdiki commit'inde
        self.assertTrue(d["veri"]["dosya"].endswith("-ELLE.tar"))
        self.assertEqual(d["degismez"]["kontrol"], 3)
        self.assertEqual(d["teknik"]["goc"], ["mod_a 20.0.1.0.1 post-migrate"])
        islemler = [tur for _db, tur, _m, _k in self.komut.prova_calismalari]
        self.assertEqual(islemler, ["neutralize", "shell", "-u", "shell"])
        self.assertEqual({db for db, *_ in self.komut.prova_calismalari}, {"pnl_deneme_prova"})
        kodlar = [k for _db, tur, _m, k in self.komut.prova_calismalari if tur == "shell"]
        self.assertTrue(kodlar[0].endswith(self.ilk) and kodlar[1].endswith(ikinci))  # eski kod, sonra yeni kod
        self.assertTrue(self.komut.prova_calismalari[2][3].endswith(ikinci))
        self.assertEqual(d["belge_duman"]["durum"], "gecti")
        self.assertEqual(d["belge_duman"]["belge"]["sayi"], 1)
        self.assertEqual(d["belge_duman"]["duman"]["senaryolar"], {"kdv1": "atlandi", "satis": "ayni"})
        # belge içeriği (özetler) iş günlüğüne yazılmadı
        self.assertNotIn("VEKOSIS_DUMAN=", self.is_sonucu(self.s.isler.liste(odoo="deneme", sinir=1)[0])["cikti"])
        self.assertNotIn(("vtest-postgres", "pnl_deneme_prova"), self.komut.veritabanlari)
        # üretime dokunulmadı: konteyner çalışıyor, commit değişmedi
        self.assertEqual(self.komut.konteynerler["pnl-deneme"], "running")
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "production")["commit"], self.ilk)
        # geçici yapılandırma kaldı mı
        self.assertFalse(list(self.ayar.gecici.glob(".prova-*")))

    def test_degismez_bozulursa_prova_duser(self):
        self.commit({"mod_a/models/a.py": "x = 2\n"}, "[FIX] mod_a")
        self.komut.degismez_bozan = True
        sonuc = self.prova()
        self.assertEqual(sonuc["durum"], "hata")
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "dustu")
        self.assertEqual(d["degismez"]["farklar"][0]["anahtar"], "yevmiye.1")
        self.assertIn("muhasebe değişmezinde 1 fark", d["neden"][0])
        self.assertNotIn(("vtest-postgres", "pnl_deneme_prova"), self.komut.veritabanlari)

    def test_guncelleme_hatasinda_prova_duser(self):
        self.commit({"mod_b/models/b.py": "y = 2\n"}, "[FIX] mod_b")
        self.komut.guncelleme_hatasi = True
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "dustu")
        self.assertIn("ERROR", d["neden"][0])
        self.assertNotIn(("vtest-postgres", "pnl_deneme_prova"), self.komut.veritabanlari)

    def test_yayin_notundaki_beklenen_fark_dusurmez(self):
        self.commit({"mod_a/models/a.py": "x = 3\n",
                     "YAYIN_NOTU.md": "# Yayın\n\n## Beklenen veri değişiklikleri\n\n- yevmiye: bilinçli göç\n"},
                    "[MIG] mod_a")
        self.komut.degismez_bozan = True
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "gecti")
        self.assertEqual(d["degismez"]["izinli"], ["yevmiye"])
        self.assertEqual(len(d["degismez"]["izinli_farklar"]), 1)

    def test_baska_committeki_yedek_yerine_taze_dokum(self):
        # tek yedek deploy öncesi yedek: ortam o zaman başka commit'teydi, kullanılmaz
        self.assertEqual(len(self.s.yedekler.liste("deneme", "production")), 1)
        self.commit({"mod_a/models/a.py": "x = 4\n"}, "[IMP] mod_a")
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["veri"]["tur"], "dokum")
        self.assertEqual(d["durum"], "gecti")

    def test_guncellenecek_yoksa_veri_provasi_yok(self):
        self.commit({"README.md": "belge\n"}, "[DOC]")
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "gecti")
        self.assertIn("gerekmedi", d["not"])
        self.assertEqual(self.komut.prova_calismalari, [])

    def test_deploy_kapisi(self):
        self.s.provalar.ayar_yaz("deneme", {"zorunlu": True})
        ikinci = self.commit({"mod_a/models/a.py": "x = 5\n"}, "[IMP] mod_a")
        sonuc = self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))
        d = self.s.deploylar.kayit_oku("deneme", "production", 2)
        self.assertEqual(sonuc["durum"], "hata")
        self.assertEqual(d["durum"], "durdu")
        self.assertIn("geçmiş bir prova yok", d["engel"])
        self.assertEqual((sonuc["sonuc"]["prova_gerekli"], sonuc["sonuc"]["commit"]), (True, ikinci))  # ekran önerir
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "production")["commit"], self.ilk)
        # düşen prova kapıyı açmaz; iş penceresi nedeni "Prova düştü" diye gösterir
        self.komut.degismez_bozan = True
        dusen = self.prova()
        self.assertTrue(dusen["sonuc"]["hata"].startswith("Prova düştü: muhasebe değişmezinde 1 fark"))
        self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))
        self.assertEqual(self.s.deploylar.kayit_oku("deneme", "production", 3)["durum"], "durdu")
        # geçen prova açar
        self.komut.degismez.clear()
        self.prova()
        sonuc = self.is_sonucu(self.s.deploylar.baslat("deneme", "production"))
        d = self.s.deploylar.kayit_oku("deneme", "production", 4)
        self.assertEqual(d["durum"], "tamam", sonuc.get("cikti"))
        self.assertEqual(d["prova"], 2)
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "production")["commit"], ikinci)

    def test_staging_deploy_kapiya_bagli_degil(self):
        self.s.provalar.ayar_yaz("deneme", {"zorunlu": True})
        st = self.commit({"mod_a/models/a.py": "x = 6\n"}, "[IMP] staging", dal="staging")
        self.depo_bagla(staging="staging")
        sonuc = self.is_sonucu(self.s.staging.olustur("deneme"))
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("cikti"))
        d = self.s.deploylar.kayit_oku("deneme", "staging", 1)
        self.assertEqual((d["durum"], d["moduller"]), ("tamam", ["mod_a"]))  # modül güncellendi, prova istenmedi
        self.assertEqual(self.s.ortamlar.gerekli("deneme", "staging")["commit"], st)

    def _yeni_duman(self, **degisen):
        import copy
        yeni = copy.deepcopy(self.komut.duman_varsayilan)
        for anahtar, deger in degisen.items():
            yeni[anahtar] = deger
        return yeni

    def test_ubl_beklenmeyen_degisiklik_duser_beklenen_gecer(self):
        yeni_ubl = {"7": {"yaprak": {"Invoice/cbc:ID[1]": "a1", "Invoice/cac:TaxTotal[1]/cbc:TaxAmount[1]": "b2",
                                     "Invoice/cac:TaxTotal[1]/cac:TaxSubtotal[1]/cbc:CalculationSequenceNumeric[1]": "c3"},
                          "gonderilmis": True, "xsd": True}}
        self.commit({"mod_a/models/a.py": "x = 6\n"}, "[IMP] mod_a")
        self.komut.duman_sirasi = [self.komut.duman_varsayilan, self._yeni_duman(ubl=yeni_ubl)]
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "dustu")
        self.assertEqual(d["belge_duman"]["belge"]["beklenmeyen"], {"CalculationSequenceNumeric": 1})
        self.assertIn("UBL'de yayın notunda bildirilmemiş değişiklik: CalculationSequenceNumeric (1)", d["neden"][0])
        # aynı değişiklik yayın notunda bildirilmişse geçer
        self.commit({"mod_a/models/a.py": "x = 7\n", "YAYIN_NOTU.md":
                     "# Yayın\n\n## Beklenen belge değişiklikleri\n\n- cbc:CalculationSequenceNumeric: KDV satırı\n"},
                    "[FIX] mod_a")
        self.komut.duman_sirasi = [self.komut.duman_varsayilan, self._yeni_duman(ubl=yeni_ubl)]
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 2)
        self.assertEqual(d["durum"], "gecti", d.get("neden"))
        self.assertEqual(d["belge_duman"]["belge"]["ogeler"], {"CalculationSequenceNumeric": 1})

    def test_sema_bozulursa_ve_duman_farkinda_duser(self):
        self.commit({"mod_a/models/a.py": "x = 8\n"}, "[IMP] mod_a")
        gecersiz = {"7": {**self.komut.duman_varsayilan["ubl"]["7"], "xsd": False, "xsd_hata": "Element '…' not expected"}}
        self.komut.duman_sirasi = [self.komut.duman_varsayilan,
                                   self._yeni_duman(ubl=gecersiz, duman={"satis": {"taslak": {"toplam": 3600.0}},
                                                                         "kdv1": {"atlandi": "modül yok"}})]
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "dustu")
        nedenler = " | ".join(d["neden"])
        self.assertIn("1 belge yeni kodla UBL-TR şemasına uymuyor", nedenler)
        self.assertIn("duman senaryosu farklı: satis", nedenler)

    def test_yeni_kodla_kabuk_calismazsa_duser(self):
        self.commit({"mod_a/models/a.py": "x = 9\n"}, "[IMP] mod_a")
        self.komut.duman_sirasi = [self.komut.duman_varsayilan, None]
        self.prova()
        d = self.s.provalar.kayit_oku("deneme", "production", 1)
        self.assertEqual(d["durum"], "dustu")
        self.assertIn("yeni kodla belge ve duman ölçümü çalışmadı", d["neden"][0])

    def test_ayni_anda_tek_prova_ve_bagli_ortam(self):
        self.s.isler._aktif["sunucu/prova"] = "x"
        with self.assertRaises(Hata) as h:
            self.s.provalar.baslat("deneme", "production")
        self.assertEqual(h.exception.kod, 409)
