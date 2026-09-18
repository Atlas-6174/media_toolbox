# 📦 Media Toolbox CLI

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Docker Compose](https://img.shields.io/badge/Docker%20Compose-v2+-2496ED.svg?logo=docker&logoColor=white)](https://docs.docker.com/compose/)

Suite de herramientas de manipulación de medios y documentos aislada mediante micro-contenedores Docker. Procesa libros, videos, audios e imágenes sin saturar tu sistema operativo anfitrión con dependencias pesadas ni conflictos de librerías.

---

## 🏗️ Arquitectura

```mermaid
graph TD
    CLI["💻 Host CLI (tb / toolbox)\nTyper + Rich + Pydantic"]
    Storage["📁 storage/\n(input / output)"]

    CLI -->|Orquestación| Docker["🐳 Docker Engine"]
    Docker --> Calibre["📦 Calibre (ebook-convert)"]
    Docker --> FFmpeg["📦 FFmpeg (Audio, Video, WebP)"]
    Docker --> YtDlp["📦 yt-dlp (Descargas)"]
    Docker --> PDF["📦 Poppler (pdfunite)"]

    Calibre <-->|Volumen compartido| Storage
    FFmpeg <-->|Volumen compartido| Storage
    YtDlp <-->|Volumen compartido| Storage
    PDF <-->|Volumen compartido| Storage
```

---

## 🚀 Prerrequisitos
- **Docker Desktop** (Engine & Docker Compose v2+)
- **Python 3.9+**

---

## ⚙️ Instalación Rápida

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/atlas/media-toolbox.git
   cd media-toolbox
   ```
2. **Construir y descargar imágenes:**
   ```bash
   make build
   ```
3. **Instalar el comando CLI en modo editable:**
   ```bash
   make install
   ```
   *Esto habilitará el comando global `tb` en tu terminal.*

---

## 🛠️ Herramientas Disponibles

### 📚 Libros y Documentos
- **Convertir a PDF:**
  ```bash
  tb convertir [archivo] [--pagina a4|letter] [--perfil kindle|kobo|tablet] [--open]
  ```
  *Soporta `.epub`, `.mobi`, `.azw3`, `.fb2`, `.txt`, `.docx`.*

- **Unir PDFs:**
  ```bash
  tb pdf unir [archivo1.pdf archivo2.pdf ...] [--salida final.pdf] [--open]
  ```

---

### 🎬 Video y Audio
- **Extraer Audio:**
  ```bash
  tb audio [video] [--formato mp3|wav|m4a] [--open]
  ```
  *Soporta `.mp4`, `.mkv`, `.mov`, `.webm`, `.avi`, `.m4v`.*

- **Recorte Ultrarrápido (sin recodificar en 1 segundo):**
  ```bash
  tb recortar [video] --desde 00:01:00 --hasta 00:02:30 [--open]
  ```

- **Generar GIF Animado:**
  ```bash
  tb gif [video] --desde 00:00:10 --duracion 5s [--fps 15] [--ancho 480] [--open]
  ```

- **Comprimir Video (para Discord, WhatsApp o Web):**
  ```bash
  tb comprimir [video] [--perfil equilibrada|ligera|maxima] [--open]
  ```

---

### 🌐 Descargas Multimedia
- **Descargar desde URL (YouTube, Vimeo, etc.):**
  ```bash
  tb descargar <URL> [--calidad 1080p|720p|max] [--playlist] [--open]
  ```
- **Descargar directamente sólo el Audio MP3:**
  ```bash
  tb descargar <URL> --audio [--open]
  ```
  *Incrusta metadatos y carátulas automáticamente.*

---

### 🖼️ Imágenes
- **Convertir y Optimizar a WebP/JPG/PNG:**
  ```bash
  tb imagen [archivo] [--formato webp] [--calidad 80] [--ancho 1200] [--open]
  ```

---

### 📊 Sistema y Mantenimiento
- **Ver estado del almacenamiento y Docker:**
  ```bash
  tb estado
  ```
- **Limpiar carpetas de entrada y salida:**
  ```bash
  make clean
  ```
- **Ejecutar tests automatizados:**
  ```bash
  make test
  ```
- **Validar formato y estilo:**
  ```bash
  make lint
  ```

---

## 💡 Opciones Globales
- `--verbose / -v`: Muestra registros detallados del contenedor en caso de error.
- `--open / -o`: Abre automáticamente la carpeta resultante en Finder al finalizar.
- **Rutas externas:** Puedes arrastrar archivos directamente al terminal (ej. `tb audio ~/Downloads/clip.mp4`) y el toolbox los importará automáticamente.

---

## 🤝 Contribuciones y Comunidad

¡Las contribuciones son bienvenidas! Revisa los siguientes recursos para empezar:
- [Guía de Contribución](CONTRIBUTING.md)
- [Código de Conducta](CODE_OF_CONDUCT.md)
- [Historial de Cambios (Changelog)](CHANGELOG.md)

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT** - consulta el archivo [LICENSE](LICENSE) para más detalles.