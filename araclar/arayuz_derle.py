"""Arayüzü derler: panel/arayuz/* -> panel/static/{index.html, app.js, stil.css}.

Arayüz kaynağını değiştirdikten sonra çalıştırın: python araclar/arayuz_derle.py
Sürüm parametresi dosya içeriğinin özetidir; tarayıcı önbelleği eski dosyayı tutmaz.
"""
import hashlib
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
KAYNAK = KOK / "panel" / "arayuz"
HEDEF = KOK / "panel" / "static"
BETIKLER = ["tasarim.js", "temel.js", "ekran_platform.js", "ekran_odoo.js", "ekran_asistan.js", "basla.js"]


def derle():
    HEDEF.mkdir(parents=True, exist_ok=True)
    betik = "\n".join(f"/* ---- {ad} ---- */\n" + (KAYNAK / ad).read_text(encoding="utf-8") for ad in BETIKLER)
    betik = '"use strict";\n' + betik
    stil = (KAYNAK / "stil.css").read_text(encoding="utf-8")
    surum = hashlib.sha256((betik + stil).encode("utf-8")).hexdigest()[:10]
    sayfa = (KAYNAK / "sablon.html").read_text(encoding="utf-8")
    sayfa = sayfa.replace("/*FAVICON*/", (KAYNAK / "favicon.txt").read_text(encoding="utf-8").strip())
    sayfa = sayfa.replace("/*SURUM*/", surum)
    (HEDEF / "app.js").write_text(betik, encoding="utf-8", newline="\n")
    (HEDEF / "stil.css").write_text(stil, encoding="utf-8", newline="\n")
    (HEDEF / "index.html").write_text(sayfa, encoding="utf-8", newline="\n")
    (HEDEF / ".gitkeep").unlink(missing_ok=True)
    return surum


if __name__ == "__main__":
    print("arayüz derlendi:", derle())
