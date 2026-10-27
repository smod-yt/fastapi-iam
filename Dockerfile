FROM python:3.14-slim

WORKDIR /app

COPY ./requirements.txt /app

RUN pip install -r ./requirements.txt --no-cache-dir --upgrade

COPY . /app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
