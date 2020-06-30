FROM python:3.8-alpine

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install -r requirements.txt

COPY . /app

EXPOSE 5000/tcp

CMD [ "python3", "app.py" ]