# 📦 Media Toolbox CLI

Suite de herramientas de manipulación de medios y documentos aislada mediante micro-contenedores Docker. Procesa libros, videos, audios e imágenes sin saturar tu sistema operativo anfitrión con dependencias pesadas.

---

## 🚀 Prerrequisitos
- **Docker Desktop** (Engine & Docker Compose v2+)
- **Python 3.9+**

---

## ⚙️ Instalación

1. **Construir y descargar imágenes:**
   ```bash
   make build
   ```
2. **Instalar el comando CLI en modo editable:**
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

---

## 💡 Opciones Globales
- `--verbose / -v`: Muestra registros detallados del contenedor en caso de error.
- `--open / -o`: Abre automáticamente la carpeta resultante en Finder al finalizar.
- **Rutas externas:** Puedes arrastrar archivos directamente al terminal (ej. `tb audio ~/Downloads/clip.mp4`) y el toolbox los importará automáticamente.