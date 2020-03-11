FROM amd64/python:3.6
ADD / / 
RUN apt-get update && apt-get install software-properties-common7
RUN add-apt-repository ppa:mc3man/trusty-media && apt-get update
RUN apt-get install ffmpeg
RUN pip install -r requirements.txt
CMD ["python", "FGBot.py"]