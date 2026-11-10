"""GitHub deposunun sunucudaki çıplak aynası: çekme, commit'e sabit kod çıkarma, fark, commit oluşturma, gönderme.

Bağlantı türleri (odoo.json -> depo.baglanti):
  app     GitHub App jetonu (okuma + yazma; zip yüklemesi ve PR için gerekli)
  anahtar depoya özel deploy key (/opt/odoo-panel/ayar/anahtarlar/<sahip>__<depo>), salt okunur
  acik    herkese açık depo, kimliksiz okuma
Jeton komut satırına yazılmaz; git'e ortam değişkeniyle (GIT_CONFIG_*) verilir.
"""
import base64
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from .hata import Hata

DEPO_DESEN = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")
DAL_DESEN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]{0,99}$")
SHA_DESEN = re.compile(r"^[0-9a-f]{7,40}$")
BAGLANTILAR = ("app", "anahtar", "acik")
YAZAR = ("Odoo Yönetim Paneli", "panel@vekosis.com")


def depo_denetle(ad):
    ad = str(ad or "").strip()
    if ad.endswith(".git"):
        ad = ad[:-4]
    if ad.startswith("https://github.com/"):
        ad = ad[len("https://github.com/"):].strip("/")
    if not DEPO_DESEN.match(ad) or ".." in ad:
        raise Hata(400, "Depo adı sahip/depo biçiminde olmalı (ör. vekosis/ornek-addons).")
    return ad


def dal_denetle(dal):
    dal = str(dal or "").strip()
    if not DAL_DESEN.match(dal) or ".." in dal or dal.endswith((".lock", "/", ".")) or "//" in dal:
        raise Hata(400, f"Geçersiz dal adı: {dal!r}")
    return dal


def sha_denetle(sha):
    sha = str(sha or "").strip().lower()
    if not SHA_DESEN.match(sha):
        raise Hata(400, "Geçersiz commit.")
    return sha


class Depo:
    def __init__(self, ayar, komut, ad, baglanti="app", github=None):
        self.ayar = ayar
        self.komut = komut
        self.ad = depo_denetle(ad)
        if baglanti not in BAGLANTILAR:
            raise Hata(400, "Bağlantı türü app, anahtar ya da acik olmalı.")
        self.baglanti = baglanti
        self.github = github

    @property
    def ayna(self):
        return self.ayar.depolar / (self.ad.replace("/", "__") + ".git")

    @property
    def anahtar_yolu(self):
        return self.ayar.ayar_dizin / "anahtarlar" / self.ad.replace("/", "__")

    # -- kimlik
    def _uzak(self, yazma=False):
        """(url, ortam değişkenleri)"""
        if self.baglanti == "app":
            if not self.github or not self.github.app_var():
                raise Hata(400, "Depo GitHub App ile bağlı ama App bilgisi sunucuda yok.")
            jeton = self.github.jeton(self.ad)
            kimlik = base64.b64encode(f"x-access-token:{jeton}".encode()).decode()
            self.komut.gizle(kimlik)
            return f"https://github.com/{self.ad}.git", {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {kimlik}",
                "GIT_TERMINAL_PROMPT": "0",
            }
        if yazma:
            raise Hata(400, "Bu depo deploy key ile bağlı; panel depoya yazamaz. Yazma için GitHub App bağlantısı gerekir.")
        if self.baglanti == "anahtar":
            if not self.anahtar_yolu.exists():
                raise Hata(400, "Deploy key üretilmemiş.")
            bilinen = self.ayar.ayar_dizin / "known_hosts"
            ssh = (f"ssh -i {self.anahtar_yolu} -o IdentitiesOnly=yes -o BatchMode=yes "
                   f"-o StrictHostKeyChecking=yes -o UserKnownHostsFile={bilinen}")
            return f"git@github.com:{self.ad}.git", {"GIT_SSH_COMMAND": ssh, "GIT_TERMINAL_PROMPT": "0"}
        return f"https://github.com/{self.ad}.git", {"GIT_TERMINAL_PROMPT": "0"}

    def anahtar_uret(self):
        """Deploy key üretir (varsa yenisini üretmez); açık anahtarı döner."""
        yol = self.anahtar_yolu
        yol.parent.mkdir(parents=True, exist_ok=True)
        if not yol.exists():
            self.komut.calistir(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"odoo-panel {self.ad}",
                                 "-f", yol], zaman_asimi=30)
        return Path(str(yol) + ".pub").read_text(encoding="utf-8").strip()

    # -- git
    def _git(self, *args, uzak=False, yazma=False, **kw):
        ortam = dict(kw.pop("ortam", None) or {})
        komut = ["git", "--git-dir", self.ayna]
        if uzak:
            url, ek = self._uzak(yazma=yazma)
            ortam.update(ek)
            args = [url if a == "{URL}" else a for a in args]
        kw.setdefault("zaman_asimi", 600)
        return self.komut.calistir(komut + list(args), ortam=ortam or None, **kw)

    def _ayna_kur(self):
        if not (self.ayna / "HEAD").exists():
            self.ayna.parent.mkdir(parents=True, exist_ok=True)
            self.komut.calistir(["git", "init", "-q", "--bare", self.ayna])

    def getir(self, dal):
        """Dalı uzaktan çeker, son commit'i döner."""
        dal = dal_denetle(dal)
        self._ayna_kur()
        sonuc = self._git("fetch", "--no-tags", "--force", "--quiet", "{URL}", f"+refs/heads/{dal}:refs/heads/{dal}",
                          uzak=True, kontrol=False)
        if not sonuc.tamam:
            metin = sonuc.cikti or ""
            if "couldn't find remote ref" in metin:
                raise Hata(404, f"Depoda '{dal}' dalı yok.")
            raise Hata(502, f"Depo çekilemedi: {metin.strip().splitlines()[-1] if metin.strip() else sonuc.kod}")
        return self.cozumle(f"refs/heads/{dal}")

    def cozumle(self, ref):
        sonuc = self._git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", kontrol=False)
        if not sonuc.tamam or not sonuc.cikti.strip():
            raise Hata(404, f"Commit bulunamadı: {ref}")
        return sonuc.cikti.strip().splitlines()[0]

    def commit_var(self, sha):
        return self._git("cat-file", "-e", f"{sha}^{{commit}}", kontrol=False).tamam

    def cikar(self, sha, hedef):
        """Commit'in ağacını hedef klasöre çıkarır (.git olmadan). Var olan hedef silinip yeniden yazılır."""
        hedef = Path(hedef)
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = Path(tempfile.mkdtemp(prefix=".cikar-", dir=hedef.parent))
        try:
            arsiv = gecici / "kod.tar"
            self._git("archive", "--format=tar", "-o", arsiv, sha)
            icerik = gecici / "icerik"
            icerik.mkdir()
            with tarfile.open(arsiv) as tar:
                tar.extractall(icerik, filter="data")
            if hedef.exists():
                shutil.rmtree(hedef)
            icerik.rename(hedef)
        finally:
            shutil.rmtree(gecici, ignore_errors=True)
        return hedef

    def bilgi(self, sha):
        cikti = self._git("log", "-1", "--format=%H%x1f%h%x1f%s%x1f%an%x1f%ae%x1f%cI", sha).cikti
        return self._bilgi_satiri(cikti.strip())

    @staticmethod
    def _bilgi_satiri(satir):
        parca = satir.split("\x1f")
        if len(parca) < 6:
            return None
        return {"sha": parca[0], "kisa": parca[1][:7], "baslik": parca[2], "yazar": parca[3], "eposta": parca[4],
                "tarih": parca[5]}

    def aradaki(self, eski, yeni, sinir=50):
        """eski..yeni arasındaki commit'ler (yeniden eskiye)."""
        aralik = f"{eski}..{yeni}" if eski else yeni
        cikti = self._git("log", f"-{int(sinir)}", "--format=%H%x1f%h%x1f%s%x1f%an%x1f%ae%x1f%cI", aralik).cikti
        return [b for b in (self._bilgi_satiri(s) for s in cikti.strip().splitlines()) if b]

    def moduller(self, sha):
        """Commit'in kökündeki Odoo modülleri (ad kümesi)."""
        cikti = self._git("ls-tree", "-r", "--name-only", sha).cikti
        return {m.group(1) for m in re.finditer(r"^([^/\n]+)/__manifest__\.py$", cikti, re.M)}

    def dosya(self, sha, yol):
        sonuc = self._git("show", f"{sha}:{yol}", kontrol=False)
        return sonuc.cikti if sonuc.tamam else None

    def degisen_moduller(self, eski, yeni):
        """eski -> yeni arasında dosyası değişen modüller. eski yoksa yenideki bütün modüller."""
        yeni_moduller = self.moduller(yeni)
        if not eski:
            return set(yeni_moduller)
        yollar = self._git("diff", "--name-only", eski, yeni).cikti.strip().splitlines()
        degisen = {y.split("/", 1)[0] for y in yollar if "/" in y}
        return {m for m in degisen if m in yeni_moduller}

    def ata(self, eski, yeni):
        """eski, yeni'nin atası mı (yeni eskiyi içeriyor mu)?"""
        return self._git("merge-base", "--is-ancestor", eski, yeni, kontrol=False).tamam

    # -- yazma
    def commit_olustur(self, taban, kaynak_dizin, moduller, mesaj, yazar=YAZAR):
        """taban commit'in ağacında verilen modül klasörlerini kaynak_dizin'dekilerle değiştirir; yeni commit'i döner.

        Çalışma ağacı açılmaz: geçici dizin dosyası + git plumbing.
        """
        kaynak_dizin = Path(kaynak_dizin)
        self.ayar.gecici.mkdir(parents=True, exist_ok=True)
        tanimlayici, ad = tempfile.mkstemp(prefix=".index-", dir=self.ayar.gecici)
        os.close(tanimlayici)
        dizin_dosyasi = Path(ad)
        dizin_dosyasi.unlink()
        ortam = {"GIT_INDEX_FILE": str(dizin_dosyasi), "GIT_AUTHOR_NAME": yazar[0], "GIT_AUTHOR_EMAIL": yazar[1],
                 "GIT_COMMITTER_NAME": yazar[0], "GIT_COMMITTER_EMAIL": yazar[1]}
        try:
            self._git("read-tree", taban, ortam=ortam)
            for modul in moduller:
                self._git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", modul, ortam=ortam)
            self._git("--work-tree", kaynak_dizin, "add", "-f", "--", *moduller, ortam=ortam)
            agac = self._git("write-tree", ortam=ortam).cikti.strip()
            eski_agac = self._git("rev-parse", f"{taban}^{{tree}}").cikti.strip()
            if agac == eski_agac:
                return None
            return self._git("commit-tree", agac, "-p", taban, "-m", mesaj, ortam=ortam).cikti.strip()
        finally:
            dizin_dosyasi.unlink(missing_ok=True)

    def gonder(self, sha, dal, eski=None):
        """sha'yı uzak dala gönderir. eski verilirse yalnız uzak dal hâlâ oradaysa (yarış koruması)."""
        dal = dal_denetle(dal)
        args = ["push", "--quiet"]
        if eski:
            args.append(f"--force-with-lease=refs/heads/{dal}:{eski}")
        args += ["{URL}", f"{sha}:refs/heads/{dal}"]
        sonuc = self._git(*args, uzak=True, yazma=True, kontrol=False)
        if not sonuc.tamam:
            metin = sonuc.cikti.strip().splitlines()
            raise Hata(409 if "stale info" in sonuc.cikti or "rejected" in sonuc.cikti else 502,
                       f"Depoya gönderilemedi: {metin[-1] if metin else sonuc.kod}")
        self._git("update-ref", f"refs/heads/{dal}", sha)
        return sha

