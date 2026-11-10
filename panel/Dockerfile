# Odoo Yönetim Paneli web konteyneri: root olmayan kullanıcı, salt okunur dosya sistemi.
# Tek dış paket: panel içi asistan için resmî Claude SDK'sı (anthropic); geri kalan her şey standart kitaplık.
FROM python:3.12-slim
RUN pip install --no-cache-dir anthropic==2.8.0 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin panel
WORKDIR /app
COPY __init__.py __main__.py panel.py yetki.py arac.py mcp.py asistan.py /app/panel/
COPY static /app/panel/static
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PANEL_VERI=/veri PANEL_PORT=8080
USER 10001
EXPOSE 8080
CMD ["python", "-m", "panel"]
