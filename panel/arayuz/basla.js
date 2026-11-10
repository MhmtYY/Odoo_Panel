/* Açılış: tema, oturum denetimi */
(async () => {
    S.tema = depo.al("tema") || (window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.dataset.theme = S.tema;
    document.body.classList.add("oneriler-gizli");
    try {
        await benYukle();
    } catch {
        girisCiz();
        return;
    }
    S.saglik = await ajan.al("saglik").catch(() => null);
    await dene(odoolariYukle, "Odoo listesi");
    R = rotaCoz();
    ciz();
})();
