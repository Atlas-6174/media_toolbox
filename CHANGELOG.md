# Changelog

Todos los cambios notables de este proyecto serán documentados en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/)
y este proyecto se adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-18

### Añadido
- Suite CLI `tb` y `toolbox` con soporte para micro-contenedores Docker.
- Comando `convertir`: Conversión de libros digitales (EPUB, MOBI, AZW3, FB2, TXT, DOCX) a PDF mediante Calibre con reporte de progreso porcentual.
- Comando `audio`: Extracción de audio (MP3, WAV, M4A) desde múltiples formatos de video (MP4, MKV, MOV, WEBM, AVI, M4V).
- Comando `descargar`: Descarga de medios con yt-dlp, soporte para solo audio (`--audio`), carátulas/metadatos incrustados y protección contra playlists.
- Comando `recortar`: Recorte ultrarrápido de audio/video en 1 segundo sin recodificar (`-c copy`).
- Comando `gif`: Generador de GIFs animados de alta fidelidad con filtro de paleta en 2 pasos de FFmpeg.
- Comando `comprimir`: Compresión inteligente de videos con perfiles adaptativos (`equilibrada`, `ligera`, `maxima`).
- Comando `pdf unir`: Unión de documentos PDF mediante Poppler (`pdfunite`).
- Comando `imagen`: Conversión y optimización de imágenes a WebP, JPG y PNG.
- Comando `estado`: Reporte visual en tablas Rich del espacio en disco y contenedores Docker asociados.
- Portabilidad global: Ejecución de `tb` desde cualquier directorio de la máquina.
- Detección proactiva del daemon de Docker y modo detallado (`--verbose / -v`).
- Soporte para arrastrar archivos externos al terminal (`resolve_input_file`).
- Integración con notificaciones de escritorio en macOS (`notify`) y apertura automática en Finder (`--open`).
- Batería de pruebas unitarias automatizadas con `pytest`.
- Pipeline de integración continua con GitHub Actions y linter/formateador `ruff`.
