# Odoo Community imajı: resmî imaj + LibreOffice (Word/Excel -> PDF) + Türkçe düzeltme modülleri.
# derle.sh üretir; addons/ klasörünü araclar/imaj_paketle.py doldurur.
ARG ODOO_ETIKET
FROM odoo:${ODOO_ETIKET}

ARG SERI
ARG AD
ARG KUR

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui python3-uno \
        fonts-dejavu-core fonts-liberation2 fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/* \
    && command -v soffice

COPY --chown=odoo:odoo addons /mnt/vekosis-addons
USER odoo

LABEL vekosis.imaj="1" \
      vekosis.imaj.seri="${SERI}" \
      vekosis.imaj.tur="community" \
      vekosis.imaj.ad="${AD}" \
      vekosis.imaj.kur="${KUR}" \
      org.opencontainers.image.vendor="Vekosis"
