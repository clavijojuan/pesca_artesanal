# syntax=docker/dockerfile:1
FROM osgeo/gdal:ubuntu-full-3.6.0

RUN apt-get update

RUN apt-get -y install python3-pip

WORKDIR /app

EXPOSE 5000

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

CMD [ "python3", "-m" , "flask", "run", "--host=0.0.0.0"]
