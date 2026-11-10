"""Test düzeni: geçici kök, sahte Docker, gerçek git ile yerel 'uzak' depo."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ajan.ayar import Ayar
from ajan.depo import Depo
from ajan.servis import Servis

from .sahte import SahteKomut, sahte_http

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "-c", "core.autocrlf=false",
       "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false"]


def manifest(ad, surum="20.0.1.0.0", depends=("base",), data=(), python=()):
    ek = f", 'external_dependencies': {{'python': {list(python)!r}}}" if python else ""
    return (f"{{'name': '{ad}', 'version': '{surum}', 'depends': {list(depends)!r}, 'data': {list(data)!r}, "
            f"'installable': True, 'license': 'OPL-1'{ek}}}\n")


def modul(ad, surum="20.0.1.0.0", depends=("base",), python=(), ek=None):
    dosyalar = {f"{ad}/__init__.py": "from . import models\n", f"{ad}/models/__init__.py": "",
                f"{ad}/__manifest__.py": manifest(ad, surum, depends, python=python)}
    dosyalar.update(ek or {})
    return dosyalar


class Temel(unittest.TestCase):
    app = False

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="panel-test-"))
        self.ayar = Ayar(kok=self.tmp / "kok", kenar_tenants=self.tmp / "edge" / "etc" / "tenants",
                         vtest_kok=self.tmp / "vtest", saglik_suresi=0)
        self.komut = SahteKomut()
        self.http = sahte_http({
            ("GET", "/installation"): (200, {"id": 77}),
            ("POST", "/access_tokens"): (201, {"token": "ghs_sahtejeton1234567890", "expires_at": "2099-01-01T00:00:00Z"}),
            ("POST", "/pulls"): (201, {"number": 12, "html_url": "https://github.com/sahip/depo/pull/12"}),
            ("GET", "/pulls/12"): (200, {"number": 12, "state": "open", "merged": False,
                                         "html_url": "https://github.com/sahip/depo/pull/12"}),
        })
        self.s = Servis(self.ayar, komut=self.komut, http=self.http, senkron=True)
        if self.app:
            (self.ayar.ayar_dizin / "github_app.json").write_text('{"app_id": 1, "anahtar": "app.pem"}')
            (self.ayar.ayar_dizin / "app.pem").write_text("sahte")
        self.uzak = self.tmp / "uzak.git"
        self.calisma = self.tmp / "calisma"
        self._git("init", "-q", "--bare", str(self.uzak))
        self._git("clone", "-q", str(self.uzak), str(self.calisma))
        self.yama = mock.patch.object(Depo, "_uzak", lambda depo, yazma=False: (str(self.uzak), {}))
        self.yama.start()

    def tearDown(self):
        self.yama.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _git(self, *args, cwd=None):
        sonuc = subprocess.run(GIT + list(args), cwd=cwd, capture_output=True, text=True)
        if sonuc.returncode != 0:
            raise AssertionError(f"git {' '.join(args)}: {sonuc.stderr}")
        return sonuc.stdout.strip()

    def commit(self, dosyalar, mesaj="degisiklik", dal="main", sil=(), taban="main"):
        c = self.calisma
        uzak_var = bool(self._git("ls-remote", "--heads", "origin", dal, cwd=c))
        bas_var = subprocess.run(GIT + ["rev-parse", "--verify", "-q", "HEAD"], cwd=c, capture_output=True).returncode == 0
        if uzak_var:
            self._git("fetch", "-q", "origin", dal, cwd=c)
            self._git("checkout", "-q", "-B", dal, "FETCH_HEAD", cwd=c)
        elif bas_var:
            self._git("fetch", "-q", "origin", taban, cwd=c)
            self._git("checkout", "-q", "-B", dal, "FETCH_HEAD", cwd=c)
        for yol, metin in dosyalar.items():
            dosya = c / yol
            dosya.parent.mkdir(parents=True, exist_ok=True)
            dosya.write_text(metin, encoding="utf-8")
        for yol in sil:
            p = c / yol
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
        self._git("add", "-A", cwd=c)
        self._git("commit", "-q", "-m", mesaj, cwd=c)
        self._git("push", "-q", "origin", dal, cwd=c)
        return self._git("rev-parse", "HEAD", cwd=c)

    # -- hazır durumlar
    def odoo_kur(self, ad="deneme"):
        is_kaydi = self.s.kurulum.kur({"id": ad, "firma": "Deneme A.Ş.", "baslangic": "bos",
                                       "imaj": "vekosis/test20:20261108-1"}, "tester")
        sonuc = self.s.isler.oku(is_kaydi["id"])
        self.assertEqual(sonuc["durum"], "tamam", sonuc.get("hata") or sonuc.get("cikti"))
        return ad

    def kurulu_yap(self, db, *moduller):
        self.komut.veritabanlari.setdefault(("vtest-postgres", db), set()).update(moduller)

    def depo_bagla(self, ad="deneme", staging=None, kip_prod="elle", kip_st="webhook", baglanti="acik"):
        govde = {"ad": "sahip/depo", "baglanti": baglanti, "dallar": {"production": "main"},
                 "kip": {"production": kip_prod}}
        if staging:
            govde["dallar"]["staging"] = staging
            govde["kip"]["staging"] = kip_st
        return self.s.odoolar.depo_bagla(self.s.odoolar.gerekli(ad), govde)

    def is_sonucu(self, is_kaydi):
        return self.s.isler.oku(is_kaydi["id"], satir=400)
