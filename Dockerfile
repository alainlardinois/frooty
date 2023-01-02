FROM python:3
RUN apt-get update && apt-get -y install ffmpeg libffi-dev libnacl-dev python3-dev
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt
COPY . /app
ENTRYPOINT ["python", "/app/FGBot.py"]