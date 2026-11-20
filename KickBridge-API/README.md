# KickBridge-API

Backend en Python 3.12+ (FastAPI + SQLAlchemy + Alembic + SQLite local o PostgreSQL administrado + AES-256-GCM) para vincular jugadores de Minecraft (Premium y No Premium) con sus cuentas reales de Kick mediante OAuth 2.1 + PKCE y enviar mensajes al chat usando la identidad real de cada jugador.

## 1. Requisitos previos
1. Python 3.12 o superior.
2. Una aplicación en Kick (`https://kick.com/settings/developer` con 2FA habilitado):
   - **Redirect URI:** `https://api.tuservidor.com/v1/oauth/callback`
   - **Scopes:** `user:read` y `chat:write`
3. Dominio HTTPS público (recomendado: **Cloudflare Tunnel**).

## 2. Instalación y migraciones
```bash
python -m venv .venv
source .venv/bin/activate  # En Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
```

## 3. Ejecución
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

## 4. Pruebas unitarias
```bash
pytest -v
```

## 5. Compatibilidad y limitaciones de Kick

La documentación oficial define `POST /public/v1/chat`, el scope `chat:write` y los campos `type: "user"`, `content` y `broadcaster_user_id` (este último es requerido para mensajes como usuario). Sin embargo, la documentación consultada **no garantiza que una cuenta autorizada pueda escribir en cualquier canal de terceros** ni especifica todos los requisitos de elegibilidad del canal. Por ello, el soporte cross-channel no se puede prometer: KickBridge envía la solicitud con la identidad OAuth del jugador y comunica el rechazo de Kick (`403`, `429`, etc.) sin cambiar a un bot ni intentar evadir permisos. Confirma la autorización con Kick antes de depender de esta función en producción.

La documentación OAuth describe la renovación mediante `refresh_token`; KickBridge guarda de forma cifrada los tokens devueltos en la renovación. Si Kick revoca permisos o rechaza la renovación, el vínculo se invalida y se solicita volver a usar `/kickchat link`.

## 6. Desplegar la API en Vercel

Vercel puede ejecutar FastAPI como funciones Python. **No uses SQLite en Vercel:** el sistema de archivos de las funciones no es almacenamiento persistente. Crea una base PostgreSQL duradera con un proveedor externo y configura `DATABASE_URL` con su URL de conexión (preferiblemente la URL pooled del proveedor). El backend convierte las formas `postgres://` y `postgresql://` a SQLAlchemy con el driver `psycopg` incluido.

1. Importa el repositorio en Vercel y deja **Root Directory** en la raíz (`/`); este repositorio contiene solo la API.
2. Configura en Vercel las variables de `.env.example`, reemplazando `DATABASE_URL` por la conexión PostgreSQL y `PUBLIC_BASE_URL` por el dominio HTTPS de producción asignado a la API. No subas el `.env`.
3. Registra en la aplicación de Kick la Redirect URI exacta `https://<dominio-api>/v1/oauth/callback`.
4. Aplica la migración contra esa base antes de usar la API: `alembic upgrade head`, ejecutado con las variables de entorno de producción cargadas de forma segura.
5. En el servidor Paper, configura `kickbridge.api.url` con ese dominio y `kickbridge.api.token` con el token del streamer.

Vercel solo aloja la API; el plugin Java se instala en Paper y no se despliega ahí. Como alternativa al despliegue Vercel, la API puede ejecutarse en el PC del administrador con SQLite y exponerse con Cloudflare Tunnel.
