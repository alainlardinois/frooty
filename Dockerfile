FROM amd64/python:3.6
ADD / / 
RUN apt-get update && apt-get install -y ffmpeg
RUN pip install -r requirements.txt
CMD ["python", "FGBot.py"]