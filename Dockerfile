FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN pip install --requirement requirements.lock
RUN useradd --create-home --uid 10001 roboscope
COPY --chown=roboscope:roboscope . .
RUN mkdir -p /app/staticfiles && chown -R roboscope:roboscope /app/staticfiles
USER roboscope
RUN DEBUG=1 python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "75", "--access-logfile", "-", "--error-logfile", "-"]
