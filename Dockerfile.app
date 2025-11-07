FROM python:3.14-slim

WORKDIR /app

COPY ./ ./

RUN pip install --no-cache-dir uv 
RUN uv venv && uv add uvloop

EXPOSE 8888

CMD ["uv", "run", "--no-dev", "./app/main.py"]