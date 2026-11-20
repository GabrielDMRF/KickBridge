# KickBridge-Plugin

Plugin para servidores **Paper 1.21.11** (Java 21) que conecta Minecraft con **KickBridge-API**.

## Compilación en IntelliJ IDEA
1. Abre la carpeta `KickBridge-Plugin` como proyecto Maven en IntelliJ IDEA.
2. Verifica que el SDK del proyecto sea **Java 21**.
3. Ejecuta el ciclo Maven `package` desde IntelliJ IDEA.
4. Copia `target/KickBridge-Plugin-1.0.0.jar` a la carpeta `plugins/` de tu servidor Paper.

## Comandos y permisos
- `/kickchat link` (`kickbridge.link`)
- `/kickchat status` (`kickbridge.status`)
- `/kickchat unlink` (`kickbridge.unlink`)
- `/kickchat <mensaje>` (`kickbridge.chat`)
- `/kickchat reload` (`kickbridge.admin`)
