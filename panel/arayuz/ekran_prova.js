/* Ortam provası (ajan/prova.py): Deploylar sekmesindeki Provalar bölümü, prova ayrıntısı, Ayarlar'daki deploy kapısı */
const PROVA_DURUM = {
    gecti: ["Geçti", "basarili", "tik"], dustu: ["Düştü", "hata", "hata"], durdu: ["Durdu", "hata", "uyari"],
    hata: ["Hata", "hata", "hata"], calisiyor: ["Çalışıyor", "islem", "don"],
};
const PROVA_GECERLILIK_SAAT = 48;
const PROVA_GOSTERILEN = 5;
const DEGISMEZ_GRUP = {
    yevmiye: "Yevmiye", hesap: "Hesap bakiyeleri", mizan: "Mizan", acik_kalem: "Açık kalemler", fis: "Fiş sayıları",
    fis_ozet: "Fiş özetleri", mutabakat: "Kısmi eşleştirmeler", tam_mutabakat: "Tam eşleştirmeler", odeme: "Ödemeler",
    odeme_ozet: "Ödeme özeti", ebelge: "e-Belge durumları",
};
const DUMAN_SENARYO = {
    satis: "Satış faturası", alis: "Alış faturası", odeme: "Tahsilat", kur_degerleme: "Kur değerlemesi",
    kdv1: "KDV1 beyannamesi",
};
const DUMAN_SONUC = {
    ayni: ["Aynı", "basarili"], "ayni-hata": ["İki kodda aynı hata", ""], atlandi: ["Atlandı", ""], farkli: ["Farklı", "hata"],
};

/* Deploy kapısı için geçerli mi: geçti, ortam hâlâ provanın başladığı sürümde ve 48 saat dolmadı (ajan: Provalar.gecen) */
function provaGecerli(p, ort) {
    return !!(p && ort && p.durum === "gecti" && p.taban_commit === ort.commit && p.bitis
        && Date.now() - ms(p.bitis) < PROVA_GECERLILIK_SAAT * 3600e3);
}
const provaKapisiAcik = (od, ortamAd) => !!(od && od.prova_zorunlu && ortamAd === "production");
async function provalariAl(od, ortamAd, ort) {
    if (!od.depo || !panelOrtami(ort)) return [];
    return ajan.al(`odoolar/${od.id}/${ortamAd}/provalar`).then((v) => v.provalar || []).catch(() => []);
}

/* Satırdaki kısa özet: geçende ne denetlendi, düşende neden */
function provaOzet(p) {
    if (p.durum === "calisiyor") return [["", "Sürüyor."]];
    if (p.durum === "dustu") return (p.neden || []).slice(0, 2).map((n) => ["kirmizi", n]);
    if (p.durum === "durdu") return [["kirmizi", `Uyumluluk denetiminde durdu: ${p.engel || ""}`]];
    if (p.durum === "hata") return [["kirmizi", p.hata || "Prova tamamlanamadı."]];
    if (p.not) return [["", p.not]];
    const parca = [];
    const dg = p.degismez;
    if (dg) parca.push(`${sayi(dg.kontrol)} muhasebe denetimi aynı${(dg.izinli_farklar || []).length ? `, ${dg.izinli_farklar.length} beklenen fark` : ""}`);
    const bd = p.belge_duman;
    if (bd && bd.belge && bd.belge.sayi) {
        parca.push(`${sayi(bd.belge.karsilastirilan)} e-Fatura karşılaştırıldı${bd.belge.farkli ? ` (${bd.belge.farkli} belgede beklenen değişiklik)` : ""}`);
    } else if (bd && bd.durum === "olculemedi") parca.push("e-Fatura ve örnek işlemler ölçülemedi");
    if (bd && bd.duman) {
        const s = Object.values(bd.duman.senaryolar || {});
        const calisan = s.filter((x) => x !== "atlandi").length;
        if (s.length) parca.push(`${calisan} örnek işlem karşılaştırıldı`);
    }
    return parca.length ? [["", parca.join(" · ")]] : [];
}

function provaSatir(p, od, ortamAd, ort) {
    const [yazi, sinif, simge] = PROVA_DURUM[p.durum] || [p.durum, "", "bilgi"];
    const surer = p.durum === "calisiyor";
    const gecerli = provaGecerli(p, ort);
    return `<li class="satir">
        <span class="satir-ikon ${surer ? "calisiyor" : sinif}">${ikon(simge, 13, surer ? 'class="donen"' : "")}</span>
        <div>
            <div class="satir-baslik">${esc(p.baslik || "Prova")}</div>
            <div class="satir-meta"><span>#${esc(p.no)}</span><span>${esc(p.kullanici || "-")}</span>
                <span title="${esc(tarihSaat(p.baslangic))}">${esc(saat(p.baslangic))}, ${esc(goreli(p.baslangic))}</span>
                ${p.commit ? `<span title="Başlangıç sürümü → denenen commit"><span class="hash">${esc(kisa(p.taban_commit))}</span> → <span class="hash">${esc(kisa(p.commit))}</span></span>` : ""}
                ${p.moduller && p.moduller.length ? `<span class="modul-ad">${esc(p.moduller.join(", "))}</span>` : ""}
                ${p.sure != null ? `<span>${esc(p.sure)} sn</span>` : ""}</div>
            ${provaOzet(p).map(([tur, n]) => `<div class="satir-not"${tur === "kirmizi" ? "" : ' style="color:var(--soluk)"'}>${esc(n)}</div>`).join("")}
        </div>
        <div class="satir-sag">
            ${gecerli ? `<span class="etiket" title="Production bu provanın başladığı sürümde ve prova ${PROVA_GECERLILIK_SAAT} saatten yeni">${ikon("tik", 11)}deploy için geçerli</span>` : ""}
            <span class="rozet ${sinif}">${esc(yazi)}</span>
            ${surer && p.is
                ? `<button class="btn bag kucuk" data-eylem="is-ac" data-is="${esc(p.is)}">İzle</button>`
                : `<button class="btn bag kucuk" data-eylem="prova-ayrinti" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-no="${esc(p.no)}">Ayrıntı</button>`}
        </div>
    </li>`;
}

function provaBolumu(od, ortamAd, ort, provalar) {
    if (!od.depo || !panelOrtami(ort)) return "";
    const baslat = yetkili("deploy") ? `<button class="btn kucuk" data-eylem="prova-baslat" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}">${ikon("denetim", 13)}Prova başlat</button>` : "";
    const kapi = provaKapisiAcik(od, ortamAd) ? `<span class="etiket" title="Ayarlar > Prova">${ikon("anahtar", 11)}deploy prova ister</span>` : "";
    const baslik = `<div class="gecmis-baslik"><h2>Provalar</h2>${kapi}${provalar.length > PROVA_GOSTERILEN ? `<span class="soluk kucuk-yazi">son ${PROVA_GOSTERILEN} / ${provalar.length}</span>` : ""}<span class="bosluk"></span>${baslat}</div>`;
    if (!provalar.length) {
        return `<section>${baslik}<div class="kart kart-ic"><p class="soluk kucuk-yazi">Prova, bir commit'i bu ortama uygulamadan önce ortamın verisinin geçici bir kopyasında dener. Değişen modüller kopyada güncellenir; muhasebe kayıtları, e-Fatura XML'i ve örnek işlemler eski ve yeni kodla karşılaştırılır. Ortama ve kullanıcılara dokunulmaz, geçici veritabanı sonunda silinir.</p></div></section>`;
    }
    return `<section>${baslik}<div class="kart"><ul>${provalar.slice(0, PROVA_GOSTERILEN).map((p) => provaSatir(p, od, ortamAd, ort)).join("")}</ul></div></section>`;
}

/* Depoda bekleyen commit kartına: bu commit'in provası */
function provaBekleyenNotu(od, ortamAd, ort, commit, provalar) {
    if (!panelOrtami(ort)) return "";
    const p = provalar.find((x) => x.commit === commit);
    const kapi = provaKapisiAcik(od, ortamAd);
    let html;
    if (!p) html = `<p class="soluk kucuk-yazi">Bu commit için prova yapılmadı.${kapi ? " Deploy için önce provanın geçmesi gerekir." : ""}</p>`;
    else {
        const [yazi, sinif] = PROVA_DURUM[p.durum] || [p.durum, ""];
        const gecerli = provaGecerli(p, ort);
        html = `<p class="kucuk-yazi" style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap"><span class="rozet ${sinif}">Prova #${esc(p.no)}: ${esc(yazi)}</span>
            <span class="soluk">${esc(goreli(p.bitis || p.baslangic))}</span>
            <button class="btn bag kucuk" data-eylem="prova-ayrinti" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-no="${esc(p.no)}">Ayrıntı</button></p>
            ${p.durum === "gecti" && !gecerli && kapi ? `<p class="soluk kucuk-yazi">Prova süresi doldu ya da ortamın sürümü değişti; deploy için yeniden prova gerekir.</p>` : ""}`;
    }
    const yeniden = !p || p.durum !== "calisiyor";
    return html + (yetkili("deploy") && yeniden ? `<div class="dugmeler" style="margin-top:.4rem"><button class="btn kucuk" data-eylem="prova-baslat" data-odoo="${esc(od.id)}" data-ortam="${ortamAd}" data-commit="${esc(commit)}">${ikon("denetim", 13)}${p ? "Yeniden prova et" : "Önce prova et"}</button></div>` : "");
}

const provaKapanis = (odoo, ortam) => (k) => {
    const no = k.sonuc && k.sonuc.prova;
    return no ? `<button class="btn birincil" data-eylem="prova-ayrinti" data-odoo="${esc(odoo)}" data-ortam="${esc(ortam)}" data-no="${esc(no)}">Prova sonucunu aç</button>` : "";
};
EYLEM["prova-baslat"] = (el) => {
    const { odoo, ortam, commit } = el.dataset;
    const od = bulOdoo(odoo);
    const dal = od && od.depo ? od.depo.dallar[ortam] : "";
    onayPenceresi({
        baslik: `${ortamAdi(ortam)} provası`,
        metin: `${commit ? `<span class="hash">${esc(kisa(commit))}</span> commit'i` : `<code>${esc(dal || "dal")}</code> dalının son hali`} ${ortamAdi(ortam).toLowerCase()} ortamının verisinin geçici bir kopyasında denenecek.
            <ul class="uste-az" style="padding-left:1.1rem;list-style:disc">
                <li>Veri, ortamın son 24 saatteki aynı sürümlü yedeğinden açılır; böyle bir yedek yoksa taze döküm alınır.</li>
                <li>Kopya nötrleştirilir (posta, zamanlanmış işler, e-Belge kapalı). Değişen ve kurulu modüller güncellenir.</li>
                <li>Muhasebe kayıtları, e-Fatura XML'i ve örnek işlemler eski ve yeni kodla karşılaştırılır.</li>
            </ul>
            Ortama ve kullanıcılara dokunulmaz; geçici veritabanı sonunda silinir. Sunucuda aynı anda tek prova çalışır.`,
        dugme: "Provayı başlat",
        tur: "mavi",
        evet: () => isBaslat(() => ajan.gonder(`odoolar/${odoo}/${ortam}/prova`, commit ? { commit } : {}),
            `${ortamAdi(ortam)} provası`, { kapanis: provaKapanis(odoo, ortam) }),
    });
};

/* ---------- prova ayrıntısı ---------- */
const provaSatirBilgi = (ad, deger) => `<div class="bilgi-satir"><span>${esc(ad)}</span><span class="deger">${deger}</span></div>`;
const provaDeger = (v) => `<code class="kucuk-yazi" style="overflow-wrap:anywhere">${esc(String(v ?? "-").slice(0, 80))}</code>`;
function provaFarkTablosu(farklar) {
    return `<div class="tablo-kap"><table class="tablo"><thead><tr><th>Denetim</th><th>Önce</th><th>Sonra</th></tr></thead>
        <tbody>${farklar.map((f) => `<tr><td><code style="overflow-wrap:anywhere">${esc(f.anahtar)}</code></td><td>${provaDeger(f.once)}</td><td>${provaDeger(f.sonra)}</td></tr>`).join("")}</tbody></table></div>`;
}
function provaMuhasebe(p) {
    const dg = p.degismez;
    if (!dg) return `<p class="soluk kucuk-yazi">Ölçülmedi.</p>`;
    const gruplar = Object.entries(dg.gruplar || {}).map(([g, n]) => `<span class="etiket">${esc(DEGISMEZ_GRUP[g] || g)}: ${esc(n)}</span>`).join(" ");
    let html = `<p class="kucuk-yazi">${sayi(dg.kontrol)} denetim güncellemeden önce ve sonra ölçüldü. ${dg.gecti ? "Bildirilmemiş fark yok." : `<strong style="color:var(--kirmizi)">${dg.farklar.length} bildirilmemiş fark.</strong>`}</p>
        ${gruplar ? `<p class="kucuk-yazi" style="display:flex;gap:.3rem;flex-wrap:wrap">${gruplar}</p>` : ""}`;
    if (dg.farklar && dg.farklar.length) html += provaFarkTablosu(dg.farklar);
    if (dg.izinli_farklar && dg.izinli_farklar.length) {
        html += `<p class="kucuk-yazi uste-az">Yayın notunda beklenen ${dg.izinli_farklar.length} fark (provayı düşürmez):</p>${provaFarkTablosu(dg.izinli_farklar.slice(0, 20))}`;
    }
    if (dg.dengesiz && dg.dengesiz.length) html += uyariKutu("kirmizi", `Mizan dengesi bozuldu: ${dg.dengesiz.map((a) => `<code>${esc(a)}</code>`).join(", ")}`);
    return html;
}
function provaBelge(bd) {
    if (!bd) return `<p class="soluk kucuk-yazi">Ölçülmedi.</p>`;
    if (bd.durum === "olculemedi" || !bd.belge) {
        return uyariKutu("gri", "Eski ya da yeni kodla ölçüm sonuç vermedi; e-Fatura ve örnek işlemler karşılaştırılamadı. Ayrıntı iş kaydında.");
    }
    const b = bd.belge;
    if (!b.sayi) return `<p class="soluk kucuk-yazi">Karşılaştırılacak onaylı satış faturası yok.</p>`;
    const sema = !b.xsd ? "denetlenmedi (şema dosyaları yok)"
        : b.xsd_gecersiz ? `<span style="color:var(--kirmizi)">${esc(b.xsd_gecersiz)} belge yeni kodla şemaya uymuyor</span>` : "yeni kodla bütün belgeler geçerli";
    let html = `${provaSatirBilgi("Seçilen belge", `${esc(b.sayi)}${b.gonderilmis ? ` (${esc(b.gonderilmis)} gönderilmiş)` : " (hiçbiri gönderilmemiş; gönderim alanları sabit değerle dolduruldu)"}`)}
        ${provaSatirBilgi("Karşılaştırılan", esc(b.karsilastirilan))}
        ${provaSatirBilgi("XML'i değişen", esc(b.farkli))}
        ${provaSatirBilgi("UBL-TR şeması", sema)}`;
    const ogeler = Object.entries(b.ogeler || {});
    if (ogeler.length) {
        const beklenmeyen = b.beklenmeyen || {};
        html += `<div class="tablo-kap uste-az"><table class="tablo"><thead><tr><th>Değişen öğe</th><th>Belge</th><th>Yayın notu</th></tr></thead>
            <tbody>${ogeler.sort((x, y) => y[1] - x[1]).map(([ad, n]) => `<tr><td><code style="overflow-wrap:anywhere">${esc(ad)}</code></td><td>${esc(n)}</td>
                <td>${ad in beklenmeyen ? `<span class="rozet hata">Bildirilmemiş</span>` : `<span class="rozet basarili">Beklenen</span>`}</td></tr>`).join("")}</tbody></table></div>`;
    }
    if (b.hata_farki && b.hata_farki.length) {
        html += `<p class="kucuk-yazi uste-az">Üretim sonucu değişen belgeler:</p><div class="tablo-kap"><table class="tablo"><thead><tr><th>Fatura</th><th>Eski kod</th><th>Yeni kod</th></tr></thead>
            <tbody>${b.hata_farki.map((h) => `<tr><td>#${esc(h.belge)}</td><td class="kucuk-yazi">${esc(h.once)}</td><td class="kucuk-yazi">${esc(h.sonra)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    if (b.gecersiz_yeni && b.gecersiz_yeni.length) {
        html += uyariKutu("kirmizi", `Eski kodda şemaya uyan, yeni kodda uymayan belgeler:<br>${b.gecersiz_yeni.map((g) => `#${esc(g.belge)}: ${esc(g.hata || "")}`).join("<br>")}`);
    }
    const uretilemeyen = Object.entries(b.uretilemeyen || {});
    if (uretilemeyen.length) {
        html += uyariKutu("gri", `İki kodda da aynı hatayla üretilemeyen, bu yüzden karşılaştırılamayan belgeler:<br>${uretilemeyen.map(([h, n]) => `${esc(n)} belge: ${esc(h)}`).join("<br>")}`);
    }
    const xsdHata = Object.entries(b.xsd_hatalar || {});
    if (xsdHata.length && b.xsd_gecersiz) html += `<details class="uste-az"><summary class="soluk kucuk-yazi" style="cursor:pointer">Şema hataları</summary><ul class="denetim-liste">${xsdHata.map(([h, n]) => `<li>${ikon("uyari", 14, 'class="ic-sari"')}<span>${esc(n)} belge: ${esc(h)}</span></li>`).join("")}</ul></details>`;
    return html;
}
function provaDuman(bd) {
    const du = bd && bd.duman;
    if (!du) return `<p class="soluk kucuk-yazi">Ölçülmedi.</p>`;
    const izinli = new Set((du.izinli || []).map((f) => f.senaryo));
    const satirlar = Object.entries(du.senaryolar || {}).map(([ad, sonuc]) => {
        let [yazi, sinif] = DUMAN_SONUC[sonuc] || [sonuc, ""];
        if (sonuc === "farkli" && izinli.has(ad)) [yazi, sinif] = ["Farklı (yayın notunda beklenen)", "uyari"];
        return `<tr><td>${esc(DUMAN_SENARYO[ad] || ad)}</td><td><span class="rozet ${sinif}">${esc(yazi)}</span></td></tr>`;
    }).join("");
    let html = `<p class="soluk kucuk-yazi">Her işlem eski ve yeni kodla geçici kopyada yapılıp geri alınır; sonuçları (tutarlar, hesaplar, durum) karşılaştırılır.</p>
        <div class="tablo-kap"><table class="tablo"><thead><tr><th>İşlem</th><th>Sonuç</th></tr></thead><tbody>${satirlar || `<tr><td colspan="2" class="soluk">Senaryo çalışmadı.</td></tr>`}</tbody></table></div>`;
    const farklar = [...(du.farklar || []), ...(du.izinli || [])];
    if (farklar.length) {
        html += farklar.map((f) => `<details class="uste-az"><summary class="kucuk-yazi" style="cursor:pointer">${esc(DUMAN_SENARYO[f.senaryo] || f.senaryo)}: eski ve yeni sonuç</summary>
            <pre class="kayit">Eski kod: ${esc(JSON.stringify(f.once, null, 1))}\nYeni kod: ${esc(JSON.stringify(f.sonra, null, 1))}</pre></details>`).join("");
    }
    if (bd.notlar && bd.notlar.length) html += `<ul class="denetim-liste uste-az">${bd.notlar.map((n) => `<li>${ikon("bilgi", 14, 'class="soluk"')}<span class="kucuk-yazi">${esc(n)}</span></li>`).join("")}</ul>`;
    return html;
}
function provaTeknik(p) {
    const t = p.teknik;
    if (!t) return `<p class="soluk kucuk-yazi">Güncelleme çalışmadı.</p>`;
    let html = provaSatirBilgi("Çıkış kodu", esc(t.cikis));
    html += (t.hatalar || []).length
        ? `<ul class="denetim-liste uste-az">${t.hatalar.map((h) => `<li>${ikon("hata", 14, 'class="ic-kirmizi"')}<span class="kucuk-yazi" style="overflow-wrap:anywhere">${esc(h)}</span></li>`).join("")}</ul>`
        : provaSatirBilgi("Sonuç", "Hata yok; modüller güncellendi, kurulu sürümler kodla aynı");
    if ((t.goc || []).length) html += provaSatirBilgi("Çalışan göç betikleri", t.goc.map((g) => `<code>${esc(g)}</code>`).join(", "));
    return html;
}
function provaAyrintiHtml(p, od, ort) {
    const [yazi, sinif] = PROVA_DURUM[p.durum] || [p.durum, ""];
    const gecerli = provaGecerli(p, ort);
    const veri = p.veri ? (p.veri.tur === "yedek" ? `yedekten: <code class="kucuk-yazi">${esc(p.veri.dosya)}</code> (${esc(tarihSaat(p.veri.tarih))})` : "taze döküm") : "-";
    const n = p.notr;
    let kutu = "";
    if (p.durum === "dustu") kutu = uyariKutu("kirmizi", `<strong>Prova düştü.</strong><ul style="padding-left:1.1rem;margin:.3rem 0 0;list-style:disc">${(p.neden || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`);
    else if (p.durum === "durdu") kutu = uyariKutu("kirmizi", `<strong>Uyumluluk denetiminde durdu.</strong> ${esc(p.engel || "")}${(p.engeller || []).length ? `<ul style="padding-left:1.1rem;margin:.3rem 0 0;list-style:disc">${p.engeller.map((e) => `<li><code>${esc(e.modul)}</code>: ${esc(e.neden)}</li>`).join("")}</ul>` : ""}`);
    else if (p.durum === "hata") kutu = uyariKutu("kirmizi", `<strong>Prova tamamlanamadı.</strong> ${esc(p.hata || "")}`);
    else if (p.durum === "gecti") {
        const son = new Date(ms(p.bitis) + PROVA_GECERLILIK_SAAT * 3600e3);
        const sonMetin = `${iki(son.getDate())}.${iki(son.getMonth() + 1)}.${son.getFullYear()} ${iki(son.getHours())}:${iki(son.getMinutes())}`;
        const uretim = p.ortam === "production";
        kutu = uyariKutu(gecerli ? "mavi" : "gri", gecerli
            ? (uretim ? `Prova ${esc(sonMetin)} saatine kadar geçerli: production'ın sürümü değişmezse bu commit'in deploy'u prova kapısından geçer.${provaKapisiAcik(od, "production") ? "" : " Bu platformda prova şu an zorunlu değil."}`
                : "Prova geçerli: ortam hâlâ provanın başladığı sürümde.")
            : p.taban_commit !== (ort && ort.commit) ? "Ortamın sürümü prova başladıktan sonra değişti; bu sonuç artık o sürüme göre değil. Deploy için yeniden prova gerekir."
                : `Prova ${PROVA_GECERLILIK_SAAT} saatten eski; deploy için yeniden prova gerekir.`, gecerli ? "tik" : "saat");
    }
    if (p.not) kutu += uyariKutu("gri", esc(p.not));
    const veriProvasi = !!(p.degismez || p.teknik || p.belge_duman);
    return `<p class="kucuk-yazi" style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center"><span class="rozet ${sinif}">${esc(yazi)}</span>
            ${p.commit ? `<span class="hash">${esc(kisa(p.commit))}</span>` : ""}<span>${esc(p.baslik || "")}</span></p>
        ${kutu}
        ${provaSatirBilgi("Başlangıç", `${esc(tarihSaat(p.baslangic))}${p.sure != null ? ` (${esc(p.sure)} sn)` : ""}`)}
        ${provaSatirBilgi("Başlatan", esc(p.kullanici || "-"))}
        ${provaSatirBilgi("Sürüm", `<span class="hash">${esc(kisa(p.taban_commit))}</span> → <span class="hash">${esc(kisa(p.commit))}</span>${p.dal ? ` <code>${esc(p.dal)}</code>` : ""}`)}
        ${provaSatirBilgi("Güncellenen modüller", esc((p.moduller || []).join(", ") || "yok"))}
        ${p.yeni_moduller && p.yeni_moduller.length ? provaSatirBilgi("Kurulmayan yeni modüller", esc(p.yeni_moduller.join(", "))) : ""}
        ${p.paketler && p.paketler.length ? provaSatirBilgi("Python paketleri", esc(p.paketler.join(", "))) : ""}
        ${p.uyumluluk && p.uyumluluk.uyari ? provaSatirBilgi("Uyumluluk", `${esc(p.uyumluluk.uyari)} uyarı`) : ""}
        ${veriProvasi ? provaSatirBilgi("Veri", veri) : ""}
        ${n ? provaSatirBilgi("Nötrleştirme sonrası", `çalışan zamanlanmış iş ${esc(n.cron ?? "-")}, etkin posta sunucusu ${esc(n.posta ?? "-")}`) : ""}
        ${veriProvasi ? `<h4 class="uste">Muhasebe kayıtları</h4>${provaMuhasebe(p)}
            <h4 class="uste">e-Fatura XML'i (UBL-TR)</h4>${provaBelge(p.belge_duman)}
            <h4 class="uste">Örnek işlemler</h4>${provaDuman(p.belge_duman)}
            <h4 class="uste">Modül güncellemesi</h4>${provaTeknik(p)}` : ""}
        <div class="dugmeler">
            ${gecerli && yetkili("deploy") ? `<button class="btn birincil" data-eylem="deploy" data-odoo="${esc(od.id)}" data-ortam="${esc(p.ortam)}" data-commit="${esc(p.commit)}">${ikon("deploy", 14)}Bu commit'i deploy et</button>` : ""}
            ${p.is ? `<button class="btn" data-eylem="is-ac" data-is="${esc(p.is)}">${ikon("log", 14)}İş kaydı</button>` : ""}
            <button class="btn ${gecerli && yetkili("deploy") ? "" : "birincil"}" data-eylem="pencere-kapat">Kapat</button></div>`;
}
EYLEM["prova-ayrinti"] = (el) => dene(async () => {
    const { odoo, ortam, no } = el.dataset;
    const p = await ajan.al(`odoolar/${odoo}/${ortam}/provalar/${no}`);
    const od = bulOdoo(odoo) || { id: odoo, ortamlar: {} };
    pencereAc(`Prova #${esc(p.no)}: ${esc(ortamAdi(p.ortam))}`, provaAyrintiHtml(p, od, od.ortamlar[p.ortam]), { genis: true });
}, "Prova kaydı");

/* ---------- Ayarlar: deploy kapısı ---------- */
function provaAyarBolumu(od) {
    if (od.tur !== "panel" || !od.depo || !yetkili("github")) return "";
    const otomatik = od.depo.kip && od.depo.kip.production === "webhook";
    return `<section class="kart kart-ic">
        <h2 style="margin-bottom:.35rem">Prova</h2>
        <div class="anahtar-satir"><div>Production deploy'undan önce prova zorunlu
            <small>Açıkken production deploy'u, aynı commit için production şimdiki sürümündeyken başlatılmış ve son ${PROVA_GECERLILIK_SAAT} saatte geçmiş bir prova ister; yoksa hiçbir şeye dokunmadan durur. Güncellenecek kurulu modül yoksa prova istenmez. Staging bu kurala bağlı değildir.${otomatik ? " Production push gelince otomatik güncelleniyor: provası yapılmamış push'ların deploy'u durur." : ""}</small></div>
            <label class="anahtar"><input type="checkbox" data-degis="prova-zorunlu" data-odoo="${esc(od.id)}" ${od.prova_zorunlu ? "checked" : ""} aria-label="Production deploy'undan önce prova zorunlu"><span></span></label></div>
    </section>`;
}
DEGIS["prova-zorunlu"] = async (el) => {
    const v = await dene(() => ajan.gonder(`odoolar/${el.dataset.odoo}/prova-ayari`, { zorunlu: el.checked }), "Prova ayarı");
    if (!v) { el.checked = !el.checked; return; }
    bildir(v.prova_zorunlu ? "Production deploy'u artık geçmiş bir prova ister." : "Prova zorunluluğu kaldırıldı.");
    await dene(odoolariYukle);
};
