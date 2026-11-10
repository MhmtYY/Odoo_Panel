"""Komut satırı.

  python3 -m ajan                 HTTP sunucusu (systemd hizmeti)
  python3 -m ajan gece-yedegi     çalışan ajana gece yedeği isteği gönderir (systemd zamanlayıcısı)
  python3 -m ajan saglik          çalışan ajanın sağlık yanıtı
"""
import json
import sys
import urllib.request

from . import ayar as ayar_modulu
from .servis import Servis
from .sunucu import calistir


def _anahtar(ayar):
    yol = ayar.ayar_dizin / "ajan_anahtari"
    if not yol.exists():
        sys.exit(f"Ajan anahtarı yok: {yol}")
    return yol.read_text(encoding="utf-8").strip()


def _cagir(ayar, yontem, yol):
    istek = urllib.request.Request(f"http://{ayar.adres}:{ayar.port}/{yol}", method=yontem,
                                   data=b"{}" if yontem == "POST" else None,
                                   headers={"X-Ajan-Anahtar": _anahtar(ayar), "X-Panel-Kullanici": "zamanlayici",
                                            "Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=60) as yanit:
        print(json.dumps(json.loads(yanit.read()), ensure_ascii=False, indent=1))


def main(argv):
    ayar = ayar_modulu.ortamdan()
    if not argv:
        calistir(Servis(ayar), _anahtar(ayar))
        return 0
    if argv[0] == "gece-yedegi":
        _cagir(ayar, "POST", "gece-yedegi")
        return 0
    if argv[0] == "saglik":
        _cagir(ayar, "GET", "saglik")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
