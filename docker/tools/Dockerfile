FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/tmp

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    mat2 \
    ghostscript \
    poppler-utils \
    libheif-examples \
    inkscape \
    icc-profiles-free \
    imagemagick \
    qpdf \
    tesseract-ocr \
    tesseract-ocr-spa \
    tesseract-ocr-eng \
    ocrmypdf \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
