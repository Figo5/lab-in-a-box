# Minimal paramiko SSH server for Lab-in-a-Box. Accepts the seeded credentials
# from env (or /labdata/users.json written by `labctl seed`) and logs every
# auth attempt, so `labctl run-brute --target ssh-lab` works out of the box.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 22
CMD ["python", "server.py"]
