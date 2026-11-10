"""JSON durum dosyaları: atomik yazma (önce geçici dosya, sonra yer değiştirme)."""
import json
import os
from datetime import datetime
from pathlib import Path


def simdi():
    return datetime.now().isoformat(timespec="seconds")


def oku(yol, varsayilan=None):
    yol = Path(yol)
    if not yol.exists():
        return varsayilan
    return json.loads(yol.read_text(encoding="utf-8"))


def yaz(yol, veri, gizli=False):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name(f".{yol.name}.{os.getpid()}.tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    if gizli:
        try:
            os.chmod(gecici, 0o600)
        except OSError:
            pass
    os.replace(gecici, yol)
    return veri
