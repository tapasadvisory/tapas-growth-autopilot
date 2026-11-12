FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AMPLIFIER_DB=/data/store.sqlite3 AMPLIFIER_HOST=0.0.0.0
WORKDIR /workspace
COPY amplifier/ /workspace/amplifier/
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin tapas && mkdir -p /data && chown tapas:tapas /data
USER tapas
EXPOSE 8765
CMD ["python","-m","amplifier"]
