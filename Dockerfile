# Explicit build so WeasyPrint's native libraries are guaranteed in the image.
FROM python:3.11-slim

# WeasyPrint runtime deps: GLib/GObject (libglib2.0-0), Pango, Cairo,
# GDK-Pixbuf, libffi, plus fonts and the shared MIME database.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway injects PORT; default for local `docker run`.
ENV PORT=8080
CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120"]
