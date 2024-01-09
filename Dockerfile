FROM python:3.9

WORKDIR /library
COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY . .

RUN find .

RUN pipdeptree
RUN python setup.py develop --no-deps
