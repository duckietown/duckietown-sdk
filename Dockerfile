FROM python:3.12

WORKDIR /library/
COPY requirements.txt .
RUN apt-get update -y
RUN apt-get install -y libturbojpeg0
RUN python3 -m pip install -r requirements.txt

COPY . .

RUN find .

RUN pipdeptree
RUN python3 -m pip install --no-deps .
