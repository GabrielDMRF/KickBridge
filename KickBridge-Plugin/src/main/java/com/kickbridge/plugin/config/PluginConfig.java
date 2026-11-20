package com.kickbridge.plugin.config;

import org.bukkit.configuration.file.FileConfiguration;

public record PluginConfig(
        String apiUrl,
        String apiToken,
        boolean chatEnabled,
        boolean requireLink,
        int chatCooldownSeconds,
        int maxLength,
        boolean linkingEnabled,
        int linkingExpirationSeconds,
        String prefix,
        String msgLinked,
        String msgUnlinked,
        String msgNotLinked,
        String msgSent,
        String msgError,
        String msgCooldown
) {
    private static final String DEFAULT_TOKEN = "TOKEN_INDIVIDUAL_DEL_STREAMER";

    public static PluginConfig fromFileConfiguration(FileConfiguration cfg) {
        String rawUrl = cfg.getString("kickbridge.api.url", "https://api.tuservidor.com").trim();
        while (rawUrl.endsWith("/")) {
            rawUrl = rawUrl.substring(0, rawUrl.length() - 1);
        }

        String token = cfg.getString("kickbridge.api.token", DEFAULT_TOKEN).trim();
        boolean chatEnabled = cfg.getBoolean("kickbridge.chat.enabled", true);
        boolean requireLink = cfg.getBoolean("kickbridge.chat.require-link", true);
        int cooldown = Math.max(0, cfg.getInt("kickbridge.chat.cooldown", 10));
        int maxLength = Math.min(500, Math.max(1, cfg.getInt("kickbridge.chat.max-length", 500)));

        boolean linkingEnabled = cfg.getBoolean("kickbridge.linking.enabled", true);
        int expiration = Math.min(900, Math.max(60, cfg.getInt("kickbridge.linking.expiration", 300)));

        String prefix = cfg.getString("kickbridge.messages.prefix", "<gold><bold>KICK</bold> <dark_gray>» <white>");
        String linked = cfg.getString("kickbridge.messages.linked", "<green>Cuenta de Kick vinculada correctamente.");
        String unlinked = cfg.getString("kickbridge.messages.unlinked", "<yellow>Cuenta de Kick desvinculada.");
        String notLinked = cfg.getString("kickbridge.messages.not-linked", "<red>Debes vincular tu cuenta con /kickchat link.");
        String sent = cfg.getString("kickbridge.messages.sent", "<green>Mensaje enviado correctamente.");
        String error = cfg.getString("kickbridge.messages.error", "<red>No se pudo enviar el mensaje.");
        String cooldownMsg = cfg.getString("kickbridge.messages.cooldown", "<red>Espera %time% segundos.");

        return new PluginConfig(
                rawUrl,
                token,
                chatEnabled,
                requireLink,
                cooldown,
                maxLength,
                linkingEnabled,
                expiration,
                prefix,
                linked,
                unlinked,
                notLinked,
                sent,
                error,
                cooldownMsg
        );
    }

    public boolean isApiUrlHttps() {
        return apiUrl.toLowerCase().startsWith("https://");
    }

    public boolean isDefaultToken() {
        return apiToken.isEmpty() || DEFAULT_TOKEN.equals(apiToken);
    }
}
