# Exponer la interfaz web de forma segura

Por defecto, `media web` publica el puerto solo en `127.0.0.1` (ver
`docker-compose.yml`) y **no tiene autenticación**. Esa es la configuración
correcta para uso local: solo quien tiene acceso a tu máquina puede llegar a
la interfaz.

Esta guía es para quien quiera ir más allá de eso: correr MediaBox en un VPS,
un servidor casero, o cualquier sitio donde la interfaz deba ser alcanzable
desde fuera de `localhost`. **No cambies `docker-compose.yml` para publicar el
puerto en `0.0.0.0` sin aplicar al menos una de las opciones de abajo** — sin
autenticación, cualquiera que llegue al puerto puede subir, leer, descargar y
borrar todo `storage/`, y el contenedor `web` tiene montado el socket de
Docker del host (`/var/run/docker.sock`), lo que equivale a control total
sobre esa máquina.

## Antes que nada: aísla el host

Dado que `web` tiene acceso al Docker daemon del host, trátalo como un
servicio con privilegios de administrador de esa máquina:

- Corre MediaBox en una VM o servidor **dedicado**, no en una máquina que
  también aloje otros servicios sensibles.
- Mantén el sistema y Docker actualizados.
- Restringe el firewall del servidor para que **solo** los puertos 80/443
  (o los que use tu reverse proxy / túnel) sean alcanzables desde fuera; el
  puerto 8000 de `web` nunca debe estar expuesto directamente a Internet.

## Opción recomendada para la mayoría: túnel administrado (sin abrir puertos)

Si no quieres lidiar con certificados ni firewalls, usa un túnel que además
resuelve TLS y, en algunos casos, autenticación:

- **Cloudflare Tunnel** (`cloudflared`): expone el servicio sin abrir ningún
  puerto entrante en tu servidor, y puedes protegerlo con Cloudflare Access
  (login con email/SSO) sin tocar el código de MediaBox.
- **Tailscale Serve/Funnel**: si solo tú (o tu equipo) necesita acceso, súmalo
  a tu tailnet con `tailscale serve` — queda disponible solo para dispositivos
  de tu red privada, sin exponer nada públicamente. `tailscale funnel` sí lo
  publica a Internet, para eso combínalo con la opción de autenticación de
  abajo.

Con cualquiera de las dos, el puerto de `web` sigue enlazado únicamente a
`127.0.0.1` (o a la red interna de Docker) tal como viene configurado; el
túnel corre como otro proceso/contenedor que reenvía el tráfico ya
autenticado hacia `127.0.0.1:8000`.

## Opción manual: reverse proxy + autenticación + TLS

Si prefieres gestionarlo tú mismo, la arquitectura recomendada es:

```
Internet -> [Caddy/Nginx: TLS + auth] -> [red interna de Docker] -> web:8000
```

`web` no debe publicar su puerto al host en absoluto en este escenario;
solo el proxy expone 80/443.

### 1. Quita la publicación de puertos de `web` y ponlo en una red interna

En un `docker-compose.override.yml` (no lo subas si tiene secretos):

```yaml
services:
  web:
    ports: []          # anula el "127.0.0.1:8000:8000" del compose base
    expose:
      - "8000"          # solo alcanzable desde otros servicios del mismo compose
    networks:
      - internal

  proxy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    networks:
      - internal
    depends_on:
      - web

networks:
  internal:

volumes:
  caddy_data:
```

### 2. Autenticación + TLS automático con Caddy

`Caddyfile` de ejemplo (Caddy obtiene el certificado TLS automáticamente vía
Let's Encrypt si `tu-dominio.com` apunta al servidor):

```
tu-dominio.com {
    basicauth {
        # genera el hash con: caddy hash-password
        tu_usuario JDJhJDE0JJ...hash_generado_con_caddy_hash_password
    }
    reverse_proxy web:8000
}
```

`basicauth` es suficiente para uso personal/pequeños equipos. Si necesitas
login con SSO, cuentas por usuario o 2FA, coloca en su lugar **Authelia** u
**oauth2-proxy** delante de `reverse_proxy web:8000` — ambos se integran bien
con Caddy o Nginx.

### 3. Nginx como alternativa (con `.htpasswd`)

```nginx
server {
    listen 443 ssl;
    server_name tu-dominio.com;

    ssl_certificate     /etc/letsencrypt/live/tu-dominio.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/tu-dominio.com/privkey.pem;

    auth_basic           "MediaBox";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Genera `.htpasswd` con `htpasswd -c /etc/nginx/.htpasswd tu_usuario`, y usa
`certbot` para obtener el certificado TLS.

## Diagnosticar fallos sin acceso interactivo

Una vez que MediaBox corre en un servidor (sin que nadie mire una terminal),
`media web` registra sus errores en `storage/logs/web.log` (rotativo, hasta
~20 MB entre el archivo activo y sus backups) además de en la salida estándar
del contenedor. Revísalo con:

```bash
tail -f storage/logs/web.log
# o, si prefieres los logs del contenedor:
docker compose logs -f web
```

## Checklist antes de exponerlo

- [ ] El puerto 8000 de `web` **no** está publicado directamente a `0.0.0.0`
      ni a Internet (solo el proxy/túnel lo está).
- [ ] Hay autenticación delante de MediaBox (basic auth como mínimo).
- [ ] El tráfico va sobre HTTPS (el proxy/túnel gestiona el certificado).
- [ ] El servidor tiene firewall activo permitiendo solo los puertos del
      proxy/túnel.
- [ ] Entiendes que quien pase la autenticación tiene, en la práctica,
      control total sobre esa máquina (por el socket de Docker) — limita
      quién tiene esas credenciales igual que limitarías el acceso SSH root.
