FROM python:3
COPY . /app
RUN apt-get update && apt-get -y install ffmpeg libffi-dev libnacl-dev python3-dev
RUN pip install -r /app/requirements.txt
ENTRYPOINT ["python", "/app/FGBot.py"]