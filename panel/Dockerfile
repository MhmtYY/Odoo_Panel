# Odoo Yönetim Paneli web konteyneri: yalnız standart Python kitaplığı, root olmayan kullanıcı, salt okunur dosya sistemi
FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin panel
WORKDIR /app
COPY __init__.py __main__.py panel.py yetki.py /app/panel/
COPY static /app/panel/static
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PANEL_VERI=/veri PANEL_PORT=8080
USER 10001
EXPOSE 8080
CMD ["python", "-m", "panel"]
