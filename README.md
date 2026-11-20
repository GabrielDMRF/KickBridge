# KickBridge

Integración de Minecraft Paper con Kick, separada en dos proyectos:

- [API](./KickBridge-API/README.md): FastAPI, OAuth 2.1 + PKCE, SQLite para desarrollo local y PostgreSQL para hosting persistente.
- [Plugin](./KickBridge-Plugin/README.md): fuentes Java para Paper 1.21.11 / Java 21.

## Despliegue

En Vercel se despliega **solo la API**: importa este repositorio y establece `KickBridge-API` como Root Directory. Configura las variables secretas descritas en `KickBridge-API/.env.example` en el panel de Vercel, usa una base PostgreSQL persistente externa en `DATABASE_URL`, y ejecuta `alembic upgrade head` contra esa base antes de activar la API. SQLite local no es persistente en las funciones de Vercel.

El plugin no se aloja en Vercel: se instala en el servidor Paper y se configura con la URL HTTPS de la API y el token individual del streamer. Consulta la documentación de cada proyecto para completar OAuth, administración y configuración.

La documentación oficial de Kick define `POST /public/v1/chat` como envío `type=user` con `broadcaster_user_id`, pero no garantiza el permiso de publicar en cualquier canal de terceros. KickBridge no suplanta identidades ni evade rechazos; un `403` se comunica como tal.
