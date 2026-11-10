"""Dış komut çalıştırıcı. Kabuk kullanılmaz; argümanlar liste olarak verilir.

Gizli değerler (token, şifre) kayda ve hata metnine "***" olarak yazılır.
Testler bu sınıfın yerine sahte bir çalıştırıcı verir (testler/sahte.py).
"""
import os
import re
import subprocess
import threading
from dataclasses import dataclass


@dataclass
class Sonuc:
    kod: int
    cikti: str = ""
    ham: bytes = b""

    @property
    def tamam(self):
        return self.kod == 0


# Sık görülen çıktılar -> kullanıcıya gösterilecek açıklama (ilk eşleşen kullanılır)
BILINEN_NEDENLER = [
    (r"No space left on device", "Sunucuda disk dolu."),
    (r"Zaman aşımı: \d+ sn|timed out|Timeout", "İşlem zaman aşımına uğradı."),
    (r"OOMKilled|Out of memory|out of memory|exit code 137", "İşlem bellek yetmediği için durduruldu."),
    (r"Cannot connect to the Docker daemon", "Docker hizmetine ulaşılamadı."),
    (r"No such container|No such object|is not running", "Konteyner bulunamadı ya da çalışmıyor."),
    (r"database \"[^\"]+\" does not exist", "Veritabanı bulunamadı."),
    (r"role \"[^\"]+\" does not exist", "Veritabanı kullanıcısı bulunamadı."),
    (r"Permission denied \(publickey\)|Could not read from remote repository|Repository not found",
     "GitHub deposuna erişilemedi: depo adı ya da erişim anahtarı yanlış."),
    (r"Could not resolve host", "Sunucu dış adrese ulaşamadı (DNS)."),
    (r"[Cc]onnection refused|could not connect to server", "Bağlantı kurulamadı; hizmet kapalı olabilir."),
    (r"[Pp]ermission denied", "Dosya ya da klasör izni yetersiz."),
    (r"Komut bulunamadı", "Sunucuda gereken program kurulu değil."),
]


def _komut_adi(args):
    a = [str(x) for x in args]
    if not a:
        return "Komut"
    if a[0] == "git":
        return "Git komutu"
    if a[0] == "docker":
        if "python3" in a or "python" in a:
            return "Odoo imajı içindeki Python betiği"
        if any(x in a for x in ("psql", "pg_dump", "pg_restore", "createdb", "dropdb")):
            return "Veritabanı komutu"
        if "compose" in a:
            return "Docker compose komutu"
        if len(a) > 1:
            return f"Docker komutu ({a[1]})"
    return f"{a[0]} komutu"


def hata_acikla(args, sonuc):
    """(kullanıcıya açıklama, teknik ayrıntı)."""
    cikti = (sonuc.cikti or "").strip()
    satirlar = cikti.splitlines()
    neden = next((metin for desen, metin in BILINEN_NEDENLER if re.search(desen, cikti)), None)
    # Python izinde son satır asıl hatadır (ör. "AttributeError: ...")
    son = next((s.strip() for s in reversed(satirlar)
                if re.match(r"^\s*[A-Za-z_.]*(Error|Exception|Exit)\b.*:", s)), None)
    if not son:
        son = next((s.strip() for s in reversed(satirlar) if re.search(r"(?i)\b(error|hata|fatal)\b", s)), None)
    son = son[:300] if son else None
    if neden and son:
        mesaj = f"{_komut_adi(args)} hata verdi: {neden} Ayrıntı: {son}"
    elif neden or son:
        mesaj = f"{_komut_adi(args)} hata verdi: {neden or son}"
    else:
        mesaj = f"{_komut_adi(args)} hata verdi (çıkış kodu {sonuc.kod})."
    gosterilen = " ".join(str(x) for x in args)
    if len(gosterilen) > 400:
        gosterilen = gosterilen[:400] + " ..."
    ayrinti = f"$ {gosterilen}\nÇıkış kodu: {sonuc.kod}\n" + "\n".join(satirlar[-25:])
    return mesaj, ayrinti


class KomutHatasi(Exception):
    def __init__(self, args, sonuc):
        self.args_ = args
        self.sonuc = sonuc
        self.kod = 500
        self.mesaj, self.ayrinti = hata_acikla(args, sonuc)
        super().__init__(self.mesaj)


class Komut:
    def __init__(self):
        self._gizliler = set()

    def gizle(self, *degerler):
        for deger in degerler:
            if deger and len(str(deger)) >= 6:
                self._gizliler.add(str(deger))

    def maskele(self, metin):
        if not metin:
            return metin
        for gizli in sorted(self._gizliler, key=len, reverse=True):
            metin = metin.replace(gizli, "***")
        return metin

    def calistir(self, args, *, girdi=None, girdi_dosya=None, cikti_dosya=None, ortam=None, cwd=None,
                 zaman_asimi=3600, log=None, ikili=False, kontrol=True):
        """Komutu çalıştırır.

        girdi       : stdin'e verilecek metin ya da bayt
        girdi_dosya : stdin bu dosyadan okunur
        cikti_dosya : stdout bu dosyaya yazılır (stderr sonuçta döner)
        log         : satır satır çağrılan işlev (uzun işlerde canlı kayıt)
        ikili       : stdout bayt olarak döner (Sonuc.ham)
        kontrol     : çıkış kodu 0 değilse KomutHatasi
        """
        args = [str(a) for a in args]
        env = None
        if ortam:
            env = dict(os.environ)
            env.update({k: str(v) for k, v in ortam.items()})
        stdin = None
        acilan = []
        try:
            if girdi_dosya is not None:
                stdin = open(girdi_dosya, "rb")
                acilan.append(stdin)
            if cikti_dosya is not None:
                cikti = open(cikti_dosya, "wb")
                acilan.append(cikti)
                sonuc = subprocess.run(args, stdin=stdin, stdout=cikti, stderr=subprocess.PIPE, env=env, cwd=cwd,
                                       timeout=zaman_asimi, input=self._bayt(girdi) if stdin is None else None)
                sonuc = Sonuc(sonuc.returncode, self.maskele(sonuc.stderr.decode("utf-8", "replace")))
            elif log is not None:
                sonuc = self._akis(args, env, cwd, zaman_asimi, log, stdin, girdi)
            else:
                ham = subprocess.run(args, stdin=stdin, capture_output=True, env=env, cwd=cwd, timeout=zaman_asimi,
                                     input=self._bayt(girdi) if stdin is None else None)
                metin = (ham.stdout if not ikili else b"").decode("utf-8", "replace") + \
                    ham.stderr.decode("utf-8", "replace")
                sonuc = Sonuc(ham.returncode, self.maskele(metin), ham.stdout if ikili else b"")
        except subprocess.TimeoutExpired:
            sonuc = Sonuc(124, f"Zaman aşımı: {zaman_asimi} sn")
        except FileNotFoundError as hata:
            sonuc = Sonuc(127, f"Komut bulunamadı: {hata}")
        finally:
            for dosya in acilan:
                dosya.close()
        if kontrol and sonuc.kod != 0:
            raise KomutHatasi([self.maskele(str(a)) for a in args], sonuc)
        return sonuc

    @staticmethod
    def _bayt(girdi):
        if girdi is None:
            return None
        return girdi.encode("utf-8") if isinstance(girdi, str) else girdi

    def _akis(self, args, env, cwd, zaman_asimi, log, stdin, girdi):
        surec = subprocess.Popen(args, stdin=stdin if stdin is not None else (subprocess.PIPE if girdi is not None else None),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd)
        zamanlayici = threading.Timer(zaman_asimi, surec.kill)
        zamanlayici.start()
        son = []
        try:
            if girdi is not None and stdin is None:
                surec.stdin.write(self._bayt(girdi))
                surec.stdin.close()
            for ham_satir in surec.stdout:
                satir = self.maskele(ham_satir.decode("utf-8", "replace").rstrip("\n"))
                log(satir)
                son.append(satir)
                if len(son) > 400:
                    del son[:200]
            kod = surec.wait()
        finally:
            zamanlayici.cancel()
        if kod == -9:
            son.append(f"Zaman aşımı: {zaman_asimi} sn")
            kod = 124
        return Sonuc(kod, "\n".join(son))
