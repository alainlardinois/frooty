FROM python:3.8
RUN apt-get update && apt-get -y install ffmpeg libffi-dev libnacl-dev python3-dev
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt --upgrade
COPY . /app
ENTRYPOINT ["python", "/app/FGBot.py"]