# KickBridge API — Documentación de Endpoints

Base URL productiva: `https://api.tuservidor.com` (HTTPS obligatorio cuando `REQUIRE_HTTPS=true`).

## Despliegue en Vercel

Configura `KickBridge-API` como Root Directory del proyecto Vercel. Vercel sirve la aplicación FastAPI desde `app/main.py`; el plugin Paper no se despliega en Vercel. Configura `DATABASE_URL` con PostgreSQL duradero y ejecuta `alembic upgrade head` contra esa misma base antes del primer uso. No uses SQLite en Vercel: el almacenamiento local de sus funciones no es persistente. Para desarrollo local, SQLite continúa siendo el valor predeterminado.

## Autenticación y cabeceras de seguridad

### Rutas del plugin (`/v1/players/*`)
- `Authorization: Bearer <STREAMER_API_TOKEN>`
- `X-KB-Timestamp`: Timestamp Unix actual en segundos (ventana `±REPLAY_WINDOW_SECONDS`).
- `X-KB-Nonce`: Identificador único por petición (`[A-Za-z0-9_-]{16,80}`).

### Rutas de administración (`/v1/admin/*`)
- `X-Admin-Token: <ADMIN_API_TOKEN>`

### Formato estándar de error
```json
{
  "error": {
    "code": "cooldown",
    "message": "Espera antes de enviar otro mensaje",
    "retry_after": 8,
    "kick_status": null
  }
}
```

## Salud
- `GET /health` -> `200 {"status": "ok"}`
- `GET /ready` -> `200 {"status": "ok"}` o `503 {"status": "unavailable"}`

## Endpoints del Plugin (`/v1`)
- `POST /v1/players/{minecraft_uuid}/link` — Body: `{"minecraft_username": "Steve", "expiration_seconds": 300}` -> `{"url": "...", "expires_in": 300}`
- `GET /v1/players/{minecraft_uuid}` -> `{"linked": true|false, ...}`
- `DELETE /v1/players/{minecraft_uuid}` -> `{"unlinked": true}`
- `POST /v1/players/{minecraft_uuid}/chat` — Body: `{"content": "..."}` -> `{"sent": true, "message_id": "..."}`

## Endpoints OAuth Públicos (`/v1/oauth`)
- `GET /v1/oauth/start/{code}` -> Redirección `302` a `https://id.kick.com/oauth/authorize` con PKCE `S256` y `state`.
- `GET /v1/oauth/callback?code=...&state=...` -> Intercambio de código, verificación de scopes `user:read chat:write` y obtención de identidad en `GET /public/v1/users`.

## Endpoints de Administración (`/v1/admin` y `/admin`)
- `GET /v1/admin/streamers`
- `POST /v1/admin/streamers`
- `PATCH /v1/admin/streamers/{id}`
- `POST /v1/admin/streamers/{id}/rotate-token`
- `POST /v1/admin/streamers/{id}/suspend`
- `POST /v1/admin/streamers/{id}/activate`
- `POST /v1/admin/streamers/{id}/revoke`
- `GET /v1/admin/streamers/{id}/accounts`
- `DELETE /v1/admin/streamers/{id}/accounts/{minecraft_uuid}`
- `GET /v1/admin/streamers/{id}/stats`
- `GET /v1/admin/audit?streamer_id=&limit=50`
- `POST /v1/admin/channels/resolve`
