"""Belge çıktısı ve duman senaryoları (Merkezi güncelleme, Aşama 2): eski kodla ve yeni kodla aynı geçici veritabanında
"odoo shell" içinde çalışır, sonuçlar karşılaştırılır.

Belge çıktısı: gönderilmiş (yoksa onaylı) satış faturalarının UBL-TR XML'i gib.ubl.builder ile yeniden üretilir.
  Her yaprak öğenin ve özniteliğin değeri yerine kısa özeti (sha256) tutulur; belge içeriği kayda ve günlüğe girmez.
  UBL-TR şeması (GİB xsdrt, /mnt/ubltr-xsd) varsa her belge şemaya göre doğrulanır.
Duman senaryoları: her biri savepoint içinde çalışır ve geri alınır (hiçbir kayıt kalmaz):
  satis    taslak satış faturası (ürün, %10 iskonto, şirketin satış vergisi), tutarlar; onay ve yevmiye satırları
  alis     aynısı alış faturası ve alış vergisiyle
  odeme    satış faturası onaylanır, ödeme sihirbazıyla tamamı ödenir; ödeme durumu ve kalan
  kur_degerleme  geçen ay sonu için kur değerlemesi hesabı (TCMB çağrısı kapalı, Odoo kur tablosu)
  kdv1     geçen ay için KDV1 beyanname taslağı hesabı
Önkoşulu olmayan senaryo "atlandi" döner. Hata da sonuçtur: eski ve yeni kodda aynı hata eşit sayılır.

Karşılaştırma: belge farkı yalnız yayın notunun "## Beklenen belge değişiklikleri" bölümündeki öğe adlarında olabilir;
duman farkı yalnız "## Beklenen veri değişiklikleri" bölümünde "duman.<senaryo>" önekiyle bildirilmişse provayı düşürmez.
"""
import json
import re
from collections import Counter

IM = "VEKOSIS_DUMAN="
XSD_YOLU = "/mnt/ubltr-xsd/maindoc/UBL-Invoice-2.1.xsd"

BETIK = r'''
import base64, datetime, hashlib, json, os, re, uuid
from odoo.exceptions import UserError

BUGUN = datetime.date.fromisoformat("__BUGUN__")
SINIR = __SINIR__
XSD = "__XSD__"
sonuc = {"surum": 1, "ubl": {}, "duman": {}, "notlar": []}
sirket = env.user.company_id


class _Geri(Exception):
    pass


def _hata(e):
    satirlar = (str(e) or "").strip().splitlines()
    return type(e).__name__ + (": " + re.sub(r"\d+", "#", satirlar[0])[:160] if satirlar else "")


def _calistir(ad, islev, hedef):
    try:
        with env.cr.savepoint():
            hedef[ad] = islev()
            raise _Geri()
    except _Geri:
        pass
    except Exception as e:  # noqa: BLE001
        hedef[ad] = {"hata": _hata(e)}
    env.invalidate_all(flush=False)


def _ozet(metin):
    return hashlib.sha256((metin or "").strip().encode("utf-8")).hexdigest()[:12]


def _yapraklar(xml):
    from lxml import etree
    kok = etree.fromstring(xml)
    cikti = {}

    def gez(el, yol):
        sayac = {}
        for cocuk in el:
            if not isinstance(cocuk.tag, str):
                continue
            ad = (cocuk.prefix + ":" if cocuk.prefix else "") + etree.QName(cocuk).localname
            sayac[ad] = sayac.get(ad, 0) + 1
            alt = f"{yol}/{ad}[{sayac[ad]}]"
            for anahtar, deger in cocuk.attrib.items():
                cikti[f"{alt}/@{etree.QName(anahtar).localname}"] = _ozet(deger)
            if len(cocuk):
                gez(cocuk, alt)
            else:
                cikti[alt] = _ozet(cocuk.text)
    gez(kok, "Invoice")
    return kok, cikti


SEMA = None
if XSD and os.path.exists(XSD):
    try:
        from lxml import etree as _et
        SEMA = _et.XMLSchema(_et.parse(XSD))
    except Exception as e:  # noqa: BLE001
        sonuc["notlar"].append("XSD yüklenemedi: " + _hata(e))


def ubl_belge(fatura):
    gonderilmis = fatura.gib_state in ("sent", "approved", "waiting")
    # Gönderilmemiş faturada gönderim anında dolan alanlar (savepoint içinde, geri alınır): ETTN ve düzenleme saati
    # iki koşuda aynı olsun diye sabit değer alır (ETTN fatura kimliğinden türetilir)
    if not fatura.gib_ettn:
        if hasattr(fatura, "_prepare_gib_fields"):
            fatura._prepare_gib_fields()
        fatura.gib_ettn = str(uuid.uuid5(uuid.NAMESPACE_OID, "vekosis-prova-%s" % fatura.id)).upper()
    if not fatura.gib_issue_time:
        fatura.gib_issue_time = "12:00:00"
    veri = env["gib.ubl.builder"].with_context(
        gib_temporary_number=fatura.gib_invoice_number or fatura.name).build_invoice_xml(fatura)
    kok, yapraklar = _yapraklar(base64.b64decode(veri))
    belge = {"yaprak": yapraklar, "gonderilmis": gonderilmis}
    if SEMA is not None:
        # Mali mühür imzasını entegratör ExtensionContent'e koyar; boş öğe şemaya uymaz. Doğrulama için yer tutucu
        for icerik in kok.iter("{urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2}"
                               "ExtensionContent"):
            if len(icerik) == 0:
                _et.SubElement(icerik, "{urn:vekosis:prova}ImzaYeri")
        belge["xsd"] = bool(SEMA.validate(kok))
        if not belge["xsd"]:
            belge["xsd_hata"] = re.sub(r"'[^']*'", "'…'", str(SEMA.error_log.last_error.message))[:200]
    return belge


if "gib.ubl.builder" in env and "gib_state" in env["account.move"]._fields:
    M = env["account.move"]
    temel = [("state", "=", "posted"), ("move_type", "in", ("out_invoice", "out_refund"))]
    gonderilmis = M.search(temel + [("gib_state", "in", ("sent", "approved", "waiting"))], order="id desc", limit=SINIR)
    diger = M.search(temel + [("id", "not in", gonderilmis.ids)], order="id desc",
                     limit=max(0, SINIR - len(gonderilmis))) if len(gonderilmis) < SINIR else M
    for fatura in gonderilmis | diger:
        _calistir(str(fatura.id), lambda fatura=fatura: ubl_belge(fatura), sonuc["ubl"])
else:
    sonuc["notlar"].append("gib_invoice kurulu değil; belge çıktısı denetlenmedi")


def _fatura(tur, vergi, adet=3, fiyat=1000.0):
    urun = env["product.product"].create({"name": "Prova ürünü", "type": "service", "list_price": fiyat,
                                          "standard_price": fiyat})
    cari = env["res.partner"].create({"name": "Prova cari", "is_company": True})
    return env["account.move"].create({
        "move_type": tur, "partner_id": cari.id, "invoice_date": BUGUN, "date": BUGUN,
        "invoice_line_ids": [(0, 0, {"product_id": urun.id, "quantity": adet, "price_unit": fiyat, "discount": 10,
                                     "tax_ids": [(6, 0, vergi.ids)]})]})


def _tutarlar(fatura):
    return {"matrah": fatura.amount_untaxed, "vergi": fatura.amount_tax, "toplam": fatura.amount_total}


def _yevmiye(fatura):
    return sorted([[l.account_id.code or "", round(l.debit, 2), round(l.credit, 2)] for l in fatura.line_ids])


def satis():
    if not sirket.account_sale_tax_id:
        return {"atlandi": "şirketin satış vergisi yok"}
    fatura = _fatura("out_invoice", sirket.account_sale_tax_id)
    sonuc_ = {"taslak": _tutarlar(fatura)}
    fatura.action_post()
    sonuc_["onay"] = {**_tutarlar(fatura), "satirlar": _yevmiye(fatura)}
    return sonuc_


def alis():
    if not sirket.account_purchase_tax_id:
        return {"atlandi": "şirketin alış vergisi yok"}
    fatura = _fatura("in_invoice", sirket.account_purchase_tax_id)
    sonuc_ = {"taslak": _tutarlar(fatura)}
    fatura.action_post()
    sonuc_["onay"] = {**_tutarlar(fatura), "satirlar": _yevmiye(fatura)}
    return sonuc_


def odeme():
    if not sirket.account_sale_tax_id:
        return {"atlandi": "şirketin satış vergisi yok"}
    fatura = _fatura("out_invoice", sirket.account_sale_tax_id)
    fatura.action_post()
    env["account.payment.register"].with_context(active_model="account.move", active_ids=fatura.ids).create(
        {"payment_date": BUGUN}).action_create_payments()
    return {"odeme_durumu": fatura.payment_state, "kalan": fatura.amount_residual}


def kur_degerleme():
    if "l10n.tr.kur.degerleme" not in env:
        return {"atlandi": "modül yok"}
    servis = type(env["l10n.tr.tcmb.service"])
    eski = servis._fetch_bulletin

    def kapali(self, *args, **kwargs):
        raise UserError("prova: TCMB çağrısı kapalı")
    servis._fetch_bulletin = kapali
    try:
        ay_sonu = BUGUN.replace(day=1) - datetime.timedelta(days=1)
        d = env["l10n.tr.kur.degerleme"].create({"tarih": ay_sonu, "company_id": sirket.id})
        d.action_hesapla()
        return {"satir": len(d.line_ids), "kar": d.toplam_kar, "zarar": d.toplam_zarar,
                "fark": round(sum(d.line_ids.mapped("fark")), 2)}
    finally:
        servis._fetch_bulletin = eski


def kdv1():
    if "gib.beyanname" not in env:
        return {"atlandi": "modül yok"}
    tur = env["gib.beyanname.type"].search([("code", "=", "KDV1")], limit=1)
    if not tur:
        return {"atlandi": "KDV1 türü yok"}
    ay = BUGUN.replace(day=1) - datetime.timedelta(days=1)
    donem_m = env["gib.beyanname.period"]
    alan = {"company_id": sirket.id, "period_type": "monthly", "year": ay.year, "month": str(ay.month)}
    donem = donem_m.search([(k, "=", v) for k, v in alan.items()], limit=1) or donem_m.create(alan)
    b = env["gib.beyanname"].create({"beyanname_type_id": tur.id, "company_id": sirket.id, "period_id": donem.id})
    b.action_compute()
    return {"matrah": b.total_taxable_amount, "vergi": b.total_tax_amount, "durum": b.state}


for _ad, _islev in (("satis", satis), ("alis", alis), ("odeme", odeme), ("kur_degerleme", kur_degerleme),
                    ("kdv1", kdv1)):
    _calistir(_ad, _islev, sonuc["duman"])

env.cr.rollback()
print("__IM__" + json.dumps(sonuc, default=str, sort_keys=True, ensure_ascii=False))
'''


def betik(bugun, sinir=10, xsd=XSD_YOLU):
    return (BETIK.replace("__BUGUN__", str(bugun)).replace("__SINIR__", str(int(sinir)))
            .replace("__XSD__", xsd or "").replace("__IM__", IM))


def cozumle(cikti):
    """Kabuk çıktısındaki sonuç satırı; yoksa None."""
    for satir in reversed((cikti or "").splitlines()):
        if satir.startswith(IM):
            try:
                return json.loads(satir[len(IM):])
            except ValueError:
                return None
    return None


def _oge(yol):
    """'Invoice/cac:TaxTotal[1]/cbc:TaxAmount[1]/@currencyID' -> 'TaxAmount@currencyID'"""
    parcalar = yol.split("/")
    if parcalar[-1].startswith("@"):
        return f"{_yerel(parcalar[-2])}{parcalar[-1]}"
    return _yerel(parcalar[-1])


def _yerel(parca):
    return re.sub(r"\[\d+\]$", "", parca).split(":")[-1]


def beklenen_belge(metin):
    """Yayın notunda '## Beklenen belge değişiklikleri' altındaki '- <öğe adı>: açıklama' satırları."""
    adlar, bolumde = [], False
    for satir in (metin or "").splitlines():
        if satir.startswith("#"):
            bolumde = "beklenen belge" in satir.lower().replace("İ", "i")
            continue
        if bolumde:
            eslesme = re.match(r"\s*[-*]\s*`?(?:[a-z]+:)?([A-Za-z][A-Za-z0-9@]*)`?\s*:", satir)
            if eslesme:
                adlar.append(eslesme.group(1))
    return adlar


def karsilastir(once, sonra, beklenen_ogeler=(), izinli_onekler=()):
    once, sonra = once or {}, sonra or {}
    ub_once, ub_sonra = once.get("ubl") or {}, sonra.get("ubl") or {}
    ogeler, farkli_belge, hata_farki, gecersiz_yeni = Counter(), 0, [], []
    uretilemeyen = Counter()  # iki kodda da aynı hatayla üretilemeyen belgeler: karşılaştırılamadı, görünür kalmalı
    for belge in sorted(set(ub_once) | set(ub_sonra)):
        a, b = ub_once.get(belge) or {}, ub_sonra.get(belge) or {}
        if "hata" in a or "hata" in b or not a or not b:
            if a.get("hata") != b.get("hata") or not a or not b:
                hata_farki.append({"belge": belge, "once": a.get("hata", "-" if not a else "üretildi"),
                                   "sonra": b.get("hata", "-" if not b else "üretildi")})
            else:
                uretilemeyen[a["hata"]] += 1
            continue
        ya, yb = a.get("yaprak") or {}, b.get("yaprak") or {}
        farkli = [y for y in set(ya) | set(yb) if ya.get(y) != yb.get(y)]
        if farkli:
            farkli_belge += 1
            ogeler.update({_oge(y) for y in farkli})
        if a.get("xsd") is True and b.get("xsd") is False:
            gecersiz_yeni.append({"belge": belge, "hata": b.get("xsd_hata")})
    beklenen = set(beklenen_ogeler)
    beklenmeyen = {ad: n for ad, n in ogeler.items() if ad not in beklenen and ad.split("@")[0] not in beklenen}
    du_once, du_sonra = once.get("duman") or {}, sonra.get("duman") or {}
    senaryolar, farklar, izinli = {}, [], []
    for ad in sorted(set(du_once) | set(du_sonra)):
        a, b = du_once.get(ad), du_sonra.get(ad)
        if a == b:
            senaryolar[ad] = "atlandi" if isinstance(a, dict) and "atlandi" in a else (
                "ayni-hata" if isinstance(a, dict) and "hata" in a else "ayni")
            continue
        senaryolar[ad] = "farkli"
        kayit = {"senaryo": ad, "once": a, "sonra": b}
        anahtar = f"duman.{ad}"
        (izinli if any(anahtar == o or anahtar.startswith(o + ".") or o == "duman" for o in izinli_onekler)
         else farklar).append(kayit)
    belgeler = len(set(ub_once) | set(ub_sonra))
    return {
        "belge": {"sayi": belgeler, "gonderilmis": sum(1 for b in ub_sonra.values() if b.get("gonderilmis")),
                  "karsilastirilan": belgeler - sum(uretilemeyen.values()) - len(hata_farki),
                  "uretilemeyen": dict(uretilemeyen.most_common(5)),
                  "farkli": farkli_belge, "ogeler": dict(ogeler), "beklenen": sorted(beklenen),
                  "beklenmeyen": beklenmeyen, "hata_farki": hata_farki[:20], "gecersiz_yeni": gecersiz_yeni[:20],
                  "xsd": any("xsd" in b for b in ub_sonra.values()),
                  "xsd_gecersiz": sum(1 for b in ub_sonra.values() if b.get("xsd") is False),
                  "xsd_hatalar": dict(Counter(b.get("xsd_hata") for b in ub_sonra.values()
                                              if b.get("xsd") is False).most_common(3))},
        "duman": {"senaryolar": senaryolar, "farklar": farklar, "izinli": izinli},
        "notlar": sorted(set(once.get("notlar") or []) | set(sonra.get("notlar") or [])),
        "gecti": not (beklenmeyen or hata_farki or gecersiz_yeni or farklar),
    }
