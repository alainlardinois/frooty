FROM python:3
COPY . /app
RUN apt-get update && apt-get -y install ffmpeg
RUN pip install -r /app/requirements.txt
VOLUME discord-config:/app/config
VOLUME discord-cogs:/app/cogs
ENTRYPOINT ["python", "/app/FGBot.py"]