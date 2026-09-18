# Guía de Contribución a Media Toolbox

¡Gracias por tu interés en contribuir a Media Toolbox! 🎉
Este proyecto busca proporcionar herramientas multimedia modulares, eficientes y aisladas mediante Docker.

---

## 🛠️ Entorno de Desarrollo

### 1. Requisitos Previos
- Python 3.9 o superior
- Docker Engine y Docker Compose v2+
- Git

### 2. Clonar e Instalar
```bash
git clone https://github.com/atlas/media-toolbox.git
cd media-toolbox

# Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar en modo editable con herramientas de desarrollo
pip install -e ".[dev]"

# Construir imágenes de Docker
make build
```

---

## 🧪 Pruebas y Calidad de Código

Antes de abrir un Pull Request, asegúrate de que todos los tests pasen y el código cumpla con los estándares de estilo:

```bash
# Ejecutar suite de pruebas
pytest tests/ -v
# o bien:
make test

# Validar formato y linting con Ruff
ruff check src tests
ruff format --check src tests
```

Para formatear el código automáticamente:
```bash
ruff check --fix src tests
ruff format src tests
```

---

## 📦 Añadir Nuevas Herramientas

Si deseas añadir una nueva herramienta multimedia:
1. Crea la clase correspondiente en `src/tools/` heredando de `src.tools.base.BaseTool` si aplica.
2. Si requiere un nuevo servicio o paquete de Docker, regístralo en `docker-compose.yml`.
3. Registra el comando en `src/main.py` usando `Typer` y tablas/barras de progreso de `Rich`.
4. Añade pruebas unitarias para parsers o argumentos en `tests/`.
5. Actualiza la documentación en `README.md` y el `Makefile`.

---

## 🌿 Flujo de Git y Pull Requests

1. Haz un fork del repositorio y crea una rama para tu función:
   ```bash
   git checkout -b feature/nueva-herramienta
   ```
2. Realiza commits descriptivos siguiendo [Conventional Commits](https://www.conventionalcommits.org/es/v1.0.0/):
   - `feat: agregar comando tb marca-de-agua`
   - `fix: corregir detección de resolución en videos verticales`
   - `docs: actualizar opciones de compresión en el README`
3. Abre un Pull Request describiendo los cambios y vinculando los issues relacionados.
