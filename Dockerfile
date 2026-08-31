FROM python:3.12-slim
WORKDIR /app
COPY . /app
ENV PYTHONPATH=src
EXPOSE 3080
# Loopback-only by default. Non-loopback bind requires QAGENT_SHELL_TOKEN.
CMD ["python", "-m", "qagent.entrypoints.shell_cli", "--serve", "--host", "127.0.0.1", "--port", "3080"]
