FROM python:3.12-slim

WORKDIR /app
COPY examples ./examples
COPY pysyncobj ./pysyncobj
COPY setup.py .
EXPOSE 45892
EXPOSE 8080

RUN python3 setup.py install --user


CMD ["python", "./examples/kvstorage_http.py"]