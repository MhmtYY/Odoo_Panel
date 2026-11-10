"""Dış komut çalıştırıcı. Kabuk kullanılmaz; argümanlar liste olarak verilir.

Gizli değerler (token, şifre) kayda ve hata metnine "***" olarak yazılır.
Testler bu sınıfın yerine sahte bir çalıştırıcı verir (testler/sahte.py).
"""
import os
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


class KomutHatasi(Exception):
    def __init__(self, args, sonuc):
        self.args_ = args
        self.sonuc = sonuc
        kuyruk = (sonuc.cikti or "").strip().splitlines()[-12:]
        super().__init__(f"Komut başarısız ({sonuc.kod}): {args[0]} {' '.join(str(a) for a in args[1:3])} ...\n"
                         + "\n".join(kuyruk))


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
            raise KomutHatasi(args, sonuc)
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
