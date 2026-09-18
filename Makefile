.PHONY: help build install epub audio descargar recortar gif comprimir imagen estado test clean clean-docker reset

# Muestra el menú de ayuda por defecto al ejecutar solo 'make'
help:
	@echo "🛠️  Media Toolbox - Comandos disponibles:"
	@echo ""
	@echo "  make build         - Construye/descarga las imágenes de Docker"
	@echo "  make install       - Instala la CLI de Python en modo editable"
	@echo "  make estado        - Muestra el espacio de almacenamiento y contenedores"
	@echo "  make epub          - Inicia la interfaz para convertir libros a PDF"
	@echo "  make audio         - Extrae pistas de audio de videos"
	@echo "  make descargar     - Descarga video/audio desde una URL (YouTube, etc.)"
	@echo "  make recortar      - Recorta audio o video sin perder calidad"
	@echo "  make gif           - Crea un GIF animado a partir de un video"
	@echo "  make comprimir     - Reduce el peso de videos pesados"
	@echo "  make imagen        - Convierte y optimiza imágenes (WebP, JPG, PNG)"
	@echo "  make test          - Ejecuta la suite de pruebas automatizadas con pytest"
	@echo "  make clean         - Limpia archivos procesados en storage/input/ y storage/output/"
	@echo "  make clean-docker  - Limpia contenedores y caché de Docker"
	@echo "  make reset         - Ejecuta clean y clean-docker juntos"

build:
	@echo "🐳 Construyendo imágenes de Docker..."
	docker compose build

install:
	@echo "🐍 Instalando dependencias de Python..."
	pip install -e .
	@echo "✅ Listo. Puedes usar 'media' en tu terminal."

web:
	media web

estado:
	media estado

epub:
	media convertir

audio:
	media audio

descargar:
	media descargar

recortar:
	media recortar

gif:
	media gif

comprimir:
	media comprimir

imagen:
	media imagen

test:
	pytest tests/ -v

lint:
	ruff check src tests

format:
	ruff format src tests
	ruff check --fix src tests

clean:
	@echo "🧹 Limpiando archivos en storage/..."
	@find storage/input -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
	@find storage/output -mindepth 1 -not -name '.gitkeep' -delete 2>/dev/null || true
	@echo "✨ Carpetas de input y output limpias."

clean-docker:
	@echo "🐳 Limpiando recursos no utilizados de Docker..."
	docker compose down --remove-orphans
	docker image prune -f
	@echo "✨ Docker limpio."

reset: clean clean-docker
	@echo "🚀 Proyecto reiniciado de fábrica."