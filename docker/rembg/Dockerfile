FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/tmp
ENV U2NET_HOME=/opt/u2net
# numba (dependencia de rembg vía pymatting) intenta cachear su JIT en disco junto
# al código fuente por defecto. Como cada ejecución en runtime es un contenedor
# efímero nuevo (`docker compose run --rm`), ese cache en disco nunca se reutiliza
# entre invocaciones de todas formas, así que simplemente lo desactivamos siempre
# en vez de perseguir permisos de escritura en site-packages para el usuario no-root.
ENV NUMBA_DISABLE_JIT=1

RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "rembg[cpu,cli]==2.0.84"

# Pre-descarga el modelo por defecto (u2net) en tiempo de build: en runtime este
# contenedor corre con network_mode: none, así que el modelo debe quedar
# horneado en la imagen para que la herramienta funcione sin red.
RUN mkdir -p ${U2NET_HOME} && chmod 777 ${U2NET_HOME} \
    && python -c "from rembg import new_session; new_session('u2net')" \
    && chmod -R a+rX ${U2NET_HOME}

WORKDIR /workspace
ENTRYPOINT ["rembg"]
