# PLACEHOLDER vulnerable SSH server for Lab-in-a-Box.
# Replace this whole directory with your existing paramiko server if you have
# one — see ssh-lab/README.md. This placeholder accepts the seeded credentials
# from env (or /labdata/users.json written by `labctl seed`) and logs every
# auth attempt, so the brute-forcer pipeline works out of the box.
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
EXPOSE 22
CMD ["python", "server.py"]
