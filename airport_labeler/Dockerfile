# A small, production-ready container for Airport Label Quest.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    AIRPORT_LABELER_DATA_DIR=/var/lib/airport-labeler

WORKDIR /app

# The game has no third-party dependencies; copy only runtime source and assets.
COPY app.py game_data.py locations_data.py yyc_ground_data.py questions.txt question_bank_curated.json ./
COPY static ./static
COPY assets ./assets

# Keep mutable player/question-bank data outside the application source tree.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /var/lib/airport-labeler \
    && chown -R appuser:appuser /app /var/lib/airport-labeler

USER appuser
EXPOSE 8000

# $PORT is supplied by most PaaS providers. The default keeps docker run convenient.
CMD ["sh", "-c", "python app.py --host 0.0.0.0 --port ${PORT:-8000}"]
