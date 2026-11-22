"""Muhasebe değişmezleri: yükseltmeden önce ve sonra aynı kalması gereken sayılar (Merkezi güncelleme, Aşama 2).

Yalnız okuyan SQL. Çıktı yalnız sayı, toplam ve özet (hash) içerir; kayıtların kendisi (ad, açıklama, kişi)
okunmaz ve sunucudan çıkmaz. Tablo ya da kolon yoksa o denetim atlanır (modül kurulu değil).

Anahtarlar (grup.alt...):
  yevmiye.<şirket>              onaylı yevmiye satırları: sayı; borç; alacak; bakiye; döviz tutarı; satır özeti
  hesap.<şirket>.<hesap>        aynısı hesap bazında (fark çıkınca yerini göstermek için)
  mizan.<şirket>                onaylı satırların bakiye toplamı (0.00 olmalı)
  acik_kalem.<şirket>           kapanmamış onaylı satırlar: sayı; kalan; dövizde kalan
  fis.<şirket>.<tür>.<durum>    fiş sayısı
  fis_ozet.<şirket>             onaylı fişlerin özeti (numara, tarih, tutar, kalan, ödeme durumu)
  mutabakat / tam_mutabakat     eşleştirme kayıtları
  odeme.<durum> / odeme_ozet    ödemeler
  ebelge.<tablo>.<kolon>.<değer> gönderilmiş e-Belgelerin durum alanları
Karşılaştırma: anahtarların değeri birebir aynı olmalı. Yayın notunda bildirilen beklenen değişiklikler (anahtar
öneki) ayrı listelenir ve provayı düşürmez.
"""
import re

KOLON_IMI = "-- vekosis-degismez-kolon"
OLCUM_IMI = "-- vekosis-degismez"

TABLOLAR = {
    "account_move_line": ["id", "move_id", "company_id", "account_id", "partner_id", "currency_id", "date", "debit",
                          "credit", "balance", "amount_currency", "amount_residual", "amount_residual_currency",
                          "reconciled", "tax_line_id", "full_reconcile_id", "parent_state"],
    "account_move": ["id", "name", "date", "move_type", "state", "journal_id", "partner_id", "currency_id",
                     "amount_total_signed", "amount_residual_signed", "payment_state", "company_id"],
    "account_partial_reconcile": ["id", "debit_move_id", "credit_move_id", "amount", "debit_amount_currency",
                                  "credit_amount_currency"],
    "account_full_reconcile": ["id"],
    "account_payment": ["id", "amount", "payment_type", "partner_id", "state", "move_id", "currency_id", "date"],
}
# e-Belge durum alanı: account_move'da yalnız e-Belge önekli durum kolonları (Odoo'nun review_state gibi kendi
# alanları değil); gib_* tablolarında durum kolonu
EBELGE_KOLON_FIS = re.compile(r"^(gib|l10n_tr|edi|archive|integrator|remote)_[a-z_]*(state|status)$")
EBELGE_KOLON_TABLO = re.compile(r"^([a-z_]*_)?(state|status)$")
EBELGE_HARIC_TABLO = {"gib_integrator"}  # nötrleştirme bu tabloyu değiştirir; belge değil

KOLON_SQL = f"""{KOLON_IMI}
SELECT table_name || '.' || column_name FROM information_schema.columns
 WHERE table_schema = 'public'
   AND (table_name IN ({", ".join(f"'{t}'" for t in TABLOLAR)}) OR table_name LIKE 'gib\\_%')
 ORDER BY 1;
"""


def _ozet(kolonlar):
    parca = ", ".join(f"coalesce({k}::text, '~')" for k in kolonlar)
    return f"coalesce(sum(hashtextextended(concat_ws('|', {parca}), 0)::numeric), 0)"


def _tam(x):
    return f"coalesce({x}, 0)"


def olcum_sql(kolon_listesi):
    """Var olan kolonlara göre ölçüm SQL'i. kolon_listesi: 'tablo.kolon' satırları."""
    var = {}
    for satir in kolon_listesi:
        tablo, _, kolon = satir.strip().partition(".")
        if tablo and kolon:
            var.setdefault(tablo, set()).add(kolon)

    def kolonlar(tablo):
        return [k for k in TABLOLAR.get(tablo, []) if k in var.get(tablo, set())]

    parcalar = [OLCUM_IMI]
    aml = kolonlar("account_move_line")
    if {"company_id", "debit", "credit", "balance", "parent_state", "account_id"} <= set(aml):
        doviz = _tam("sum(amount_currency)") if "amount_currency" in aml else "0"
        parcalar.append(f"""
SELECT 'yevmiye.' || company_id || '|' || count(*) || ';' || {_tam('sum(debit)')} || ';' || {_tam('sum(credit)')} || ';'
       || {_tam('sum(balance)')} || ';' || {doviz} || ';' || {_ozet(aml)}
  FROM account_move_line WHERE parent_state = 'posted' GROUP BY company_id;
SELECT 'hesap.' || company_id || '.' || account_id || '|' || count(*) || ';' || {_tam('sum(debit)')} || ';'
       || {_tam('sum(credit)')} || ';' || {doviz}
  FROM account_move_line WHERE parent_state = 'posted' GROUP BY company_id, account_id;
SELECT 'mizan.' || company_id || '|' || round({_tam('sum(balance)')}, 2)
  FROM account_move_line WHERE parent_state = 'posted' GROUP BY company_id;""")
        if {"amount_residual", "reconciled"} <= set(aml):
            kalan_doviz = (_tam("sum(amount_residual_currency)") if "amount_residual_currency" in aml else "0")
            parcalar.append(f"""
SELECT 'acik_kalem.' || company_id || '|' || count(*) || ';' || {_tam('sum(amount_residual)')} || ';' || {kalan_doviz}
  FROM account_move_line WHERE parent_state = 'posted' AND NOT coalesce(reconciled, false) AND amount_residual <> 0
 GROUP BY company_id;""")
    am = kolonlar("account_move")
    if {"company_id", "move_type", "state"} <= set(am):
        parcalar.append(f"""
SELECT 'fis.' || company_id || '.' || move_type || '.' || state || '|' || count(*)
  FROM account_move GROUP BY company_id, move_type, state;
SELECT 'fis_ozet.' || company_id || '|' || count(*) || ';' || {_ozet(am)}
  FROM account_move WHERE state = 'posted' GROUP BY company_id;""")
    apr = kolonlar("account_partial_reconcile")
    if "amount" in apr:
        parcalar.append(f"""
SELECT 'mutabakat|' || count(*) || ';' || {_tam('sum(amount)')} || ';' || {_ozet(apr)} FROM account_partial_reconcile;""")
    if kolonlar("account_full_reconcile"):
        parcalar.append("\nSELECT 'tam_mutabakat|' || count(*) FROM account_full_reconcile;")
    ap = kolonlar("account_payment")
    if "state" in ap:
        parcalar.append(f"""
SELECT 'odeme.' || coalesce(state, '-') || '|' || count(*) FROM account_payment GROUP BY state;
SELECT 'odeme_ozet|' || count(*) || ';' || {_ozet(ap)} FROM account_payment;""")
    for tablo in sorted(var):
        if tablo in EBELGE_HARIC_TABLO or not (tablo == "account_move" or tablo.startswith("gib_")):
            continue
        for kolon in sorted(var[tablo]):
            desen = EBELGE_KOLON_FIS if tablo == "account_move" else EBELGE_KOLON_TABLO
            if desen.match(kolon):
                parcalar.append(f"""
SELECT 'ebelge.{tablo}.{kolon}.' || coalesce({kolon}::text, '-') || '|' || count(*) FROM "{tablo}" GROUP BY {kolon};""")
    return "\n".join(parcalar) + "\n"


def cozumle(cikti):
    sonuc = {}
    for satir in (cikti or "").splitlines():
        anahtar, ayrac, deger = satir.strip().partition("|")
        if ayrac and anahtar:
            sonuc[anahtar] = deger.strip()
    return sonuc


def olc(psql):
    """psql: sql -> çıktı metni. {anahtar: değer} döner."""
    kolonlar = psql(KOLON_SQL).splitlines()
    return cozumle(psql(olcum_sql(kolonlar)))


def grup(anahtar):
    return anahtar.split(".", 1)[0]


def karsilastir(once, sonra, izinli=()):
    """Önce/sonra ölçümünü karşılaştırır. izinli: yayın notunda bildirilen anahtar önekleri."""
    farklar, izinli_farklar = [], []
    for anahtar in sorted(set(once) | set(sonra)):
        a, b = once.get(anahtar), sonra.get(anahtar)
        if a == b:
            continue
        kayit = {"anahtar": anahtar, "once": a, "sonra": b}
        (izinli_farklar if any(anahtar == o or anahtar.startswith(o + ".") for o in izinli) else farklar).append(kayit)
    gruplar = {}
    for anahtar in once:
        gruplar[grup(anahtar)] = gruplar.get(grup(anahtar), 0) + 1
    dengesiz = [a for a, d in sonra.items() if a.startswith("mizan.") and d not in ("0", "0.00", "0.0")
                and once.get(a) in ("0", "0.00", "0.0")]
    return {"kontrol": len(once), "gruplar": gruplar, "farklar": farklar, "izinli_farklar": izinli_farklar,
            "dengesiz": dengesiz, "gecti": not farklar}


def beklenen_farklar(metin):
    """Yayın notundaki '## Beklenen veri değişiklikleri' bölümünden '- <anahtar öneki>: açıklama' satırları."""
    onekler, bolumde = [], False
    for satir in (metin or "").splitlines():
        if satir.startswith("#"):
            bolumde = "beklenen veri" in satir.lower().replace("İ", "i")
            continue
        if bolumde:
            eslesme = re.match(r"\s*[-*]\s*`?([a-z_][a-z0-9_.]*)`?\s*:", satir)
            if eslesme:
                onekler.append(eslesme.group(1).rstrip("."))
    return onekler
