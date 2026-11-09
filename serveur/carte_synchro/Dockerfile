ARG BUILD_FROM
FROM python:3.12-alpine
RUN apk add --no-cache tzdata
COPY serveur.py matin.py /
CMD ["python3", "-u", "/serveur.py"]
