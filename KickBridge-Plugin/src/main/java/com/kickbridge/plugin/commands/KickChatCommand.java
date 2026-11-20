package com.kickbridge.plugin.commands;

import com.kickbridge.plugin.KickBridgePlugin;
import com.kickbridge.plugin.api.KickBridgeApiException;
import com.kickbridge.plugin.config.PluginConfig;
import com.kickbridge.plugin.managers.PlayerStateManager;
import com.kickbridge.plugin.utils.MessageUtils;
import com.kickbridge.plugin.utils.MessageValidator;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.command.TabCompleter;
import org.bukkit.entity.Player;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.CompletionException;

public final class KickChatCommand implements CommandExecutor, TabCompleter {
    private final KickBridgePlugin plugin;

    public KickChatCommand(KickBridgePlugin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(@NotNull CommandSender sender, @NotNull Command command, @NotNull String label, @NotNull String[] args) {
        MessageUtils messages = plugin.getMessageUtils();

        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        if (args.length == 1) {
            String sub = args[0].toLowerCase(Locale.ROOT);
            switch (sub) {
                case "reload" -> {
                    if (!sender.hasPermission("kickbridge.admin")) {
                        messages.sendPlainError(sender, "No tienes permiso para usar este subcomando.");
                        return true;
                    }
                    plugin.reloadPluginState();
                    plugin.getMessageUtils().sendPrefixed(sender, "<green>Configuración de KickBridge recargada.");
                    return true;
                }
                case "link" -> {
                    if (!(sender instanceof Player player)) {
                        messages.sendPlainError(sender, "Este subcomando solo puede usarse dentro del juego.");
                        return true;
                    }
                    handleLink(player);
                    return true;
                }
                case "unlink" -> {
                    if (!(sender instanceof Player player)) {
                        messages.sendPlainError(sender, "Este subcomando solo puede usarse dentro del juego.");
                        return true;
                    }
                    handleUnlink(player);
                    return true;
                }
                case "status" -> {
                    if (!(sender instanceof Player player)) {
                        messages.sendPlainError(sender, "Este subcomando solo puede usarse dentro del juego.");
                        return true;
                    }
                    handleStatus(player);
                    return true;
                }
                default -> {
                }
            }
        }

        if (!(sender instanceof Player player)) {
            messages.sendPlainError(sender, "Solo los jugadores pueden enviar mensajes al chat de Kick.");
            return true;
        }

        handleChat(player, String.join(" ", args));
        return true;
    }

    private void handleLink(Player player) {
        PluginConfig cfg = plugin.getPluginConfig();
        MessageUtils messages = plugin.getMessageUtils();

        if (!player.hasPermission("kickbridge.link")) {
            messages.sendPlainError(player, "No tienes permiso para vincular tu cuenta.");
            return;
        }
        if (!cfg.linkingEnabled()) {
            messages.sendPlainError(player, "La vinculación de cuentas está desactivada temporalmente.");
            return;
        }

        UUID uuid = player.getUniqueId();
        plugin.getApiClient().startLink(uuid, player.getName(), cfg.linkingExpirationSeconds())
                .whenComplete((response, throwable) -> Bukkit.getScheduler().runTask(plugin, () -> {
                    if (!player.isOnline()) {
                        return;
                    }
                    if (throwable != null) {
                        handleApiFailure(player, throwable, "No se pudo iniciar la vinculación.");
                        return;
                    }
                    messages.sendLinkPrompt(player, response.getUrl(), response.getExpiresIn());
                }));
    }

    private void handleUnlink(Player player) {
        MessageUtils messages = plugin.getMessageUtils();
        if (!player.hasPermission("kickbridge.unlink")) {
            messages.sendPlainError(player, "No tienes permiso para desvincular tu cuenta.");
            return;
        }

        UUID uuid = player.getUniqueId();
        plugin.getApiClient().unlinkPlayer(uuid)
                .whenComplete((ignored, throwable) -> Bukkit.getScheduler().runTask(plugin, () -> {
                    if (throwable == null) {
                        plugin.getStateManager().markUnlinked(uuid);
                        if (player.isOnline()) {
                            messages.sendPrefixed(player, plugin.getPluginConfig().msgUnlinked());
                        }
                        return;
                    }
                    if (player.isOnline()) {
                        handleApiFailure(player, throwable, "No se pudo desvincular tu cuenta.");
                    }
                }));
    }

    private void handleStatus(Player player) {
        MessageUtils messages = plugin.getMessageUtils();
        if (!player.hasPermission("kickbridge.status")) {
            messages.sendPlainError(player, "No tienes permiso para consultar el estado.");
            return;
        }

        UUID uuid = player.getUniqueId();
        plugin.getApiClient().getPlayerStatus(uuid)
                .whenComplete((status, throwable) -> Bukkit.getScheduler().runTask(plugin, () -> {
                    if (!player.isOnline()) {
                        return;
                    }
                    if (throwable != null) {
                        handleApiFailure(player, throwable, "No se pudo consultar tu estado de vinculación.");
                        return;
                    }
                    plugin.getStateManager().updateFromStatus(uuid, status);
                    if (status.isLinked()) {
                        messages.sendStatusLinked(player, status.getKickUsername());
                    } else {
                        messages.sendPrefixed(player, plugin.getPluginConfig().msgNotLinked());
                    }
                }));
    }

    private void handleChat(Player player, String rawMessage) {
        PluginConfig cfg = plugin.getPluginConfig();
        MessageUtils messages = plugin.getMessageUtils();

        if (!player.hasPermission("kickbridge.chat")) {
            messages.sendPlainError(player, "No tienes permiso para enviar mensajes a Kick.");
            return;
        }
        if (!cfg.chatEnabled()) {
            messages.sendPlainError(player, "El envío de mensajes a Kick está desactivado.");
            return;
        }

        UUID uuid = player.getUniqueId();

        if (cfg.requireLink()) {
            Optional<PlayerStateManager.CachedLinkState> cached = plugin.getStateManager().getCached(uuid);
            if (cached.isPresent() && !cached.get().linked()) {
                messages.sendPrefixed(player, cfg.msgNotLinked());
                return;
            }
        }

        long remaining = plugin.getCooldownManager().getRemainingSeconds(uuid);
        if (remaining > 0) {
            messages.sendCooldown(player, remaining);
            return;
        }

        MessageValidator.ValidationResult validation = MessageValidator.validate(rawMessage, cfg.maxLength());
        if (!validation.valid()) {
            messages.sendPlainError(player, validation.reason());
            return;
        }

        plugin.getCooldownManager().applyCooldown(uuid, cfg.chatCooldownSeconds());

        plugin.getApiClient().sendChat(uuid, validation.sanitized())
                .whenComplete((res, throwable) -> Bukkit.getScheduler().runTask(plugin, () -> {
                    if (!player.isOnline()) {
                        return;
                    }
                    if (throwable == null && res != null && res.isSent()) {
                        messages.sendPrefixed(player, cfg.msgSent());
                        return;
                    }
                    if (throwable != null) {
                        handleApiFailure(player, throwable, null);
                    } else {
                        messages.sendPrefixed(player, cfg.msgError());
                    }
                }));
    }

    private void handleApiFailure(Player player, Throwable rawThrowable, @Nullable String fallbackMessage) {
        Throwable cause = rawThrowable instanceof CompletionException && rawThrowable.getCause() != null
                ? rawThrowable.getCause()
                : rawThrowable;

        MessageUtils messages = plugin.getMessageUtils();
        PluginConfig cfg = plugin.getPluginConfig();

        if (cause instanceof KickBridgeApiException apiEx) {
            String code = apiEx.getErrorCode();
            switch (code) {
                case "not_linked" -> {
                    plugin.getStateManager().markUnlinked(player.getUniqueId());
                    messages.sendPrefixed(player, cfg.msgNotLinked());
                }
                case "reauth_required" -> {
                    plugin.getStateManager().markUnlinked(player.getUniqueId());
                    messages.sendPlainError(player, "Tu sesión de Kick expiró o perdió permisos. Usa /kickchat link.");
                }
                case "already_linked" -> messages.sendPrefixed(player, cfg.msgLinked());
                case "cooldown", "rate_limited", "kick_rate_limited" -> {
                    int retry = apiEx.getRetryAfter() != null ? apiEx.getRetryAfter() : Math.max(1, cfg.chatCooldownSeconds());
                    plugin.getCooldownManager().applyCooldown(player.getUniqueId(), retry);
                    messages.sendCooldown(player, retry);
                }
                case "kick_forbidden", "invalid_message", "message_too_long", "kick_rejected" ->
                        messages.sendPlainError(player, apiEx.getMessage());
                default -> {
                    plugin.getLogger().warning("Error API KickBridge (" + code + "): " + apiEx.getMessage());
                    if (fallbackMessage != null) {
                        messages.sendPlainError(player, fallbackMessage);
                    } else {
                        messages.sendPrefixed(player, cfg.msgError());
                    }
                }
            }
            return;
        }

        plugin.getLogger().warning("Fallo de comunicación con KickBridge API: " + cause.getMessage());
        if (fallbackMessage != null) {
            messages.sendPlainError(player, fallbackMessage);
        } else {
            messages.sendPrefixed(player, cfg.msgError());
        }
    }

    private void sendHelp(CommandSender sender) {
        MessageUtils messages = plugin.getMessageUtils();
        messages.sendPrefixed(sender, "<gold>Comandos disponibles:");
        messages.sendPrefixed(sender, "<yellow>/kickchat link <gray>- Vincula tu cuenta de Kick");
        messages.sendPrefixed(sender, "<yellow>/kickchat status <gray>- Consulta tu cuenta vinculada");
        messages.sendPrefixed(sender, "<yellow>/kickchat unlink <gray>- Desvincula tu cuenta de Kick");
        messages.sendPrefixed(sender, "<yellow>/kickchat <mensaje> <gray>- Envía un mensaje al chat de Kick");
        if (sender.hasPermission("kickbridge.admin")) {
            messages.sendPrefixed(sender, "<yellow>/kickchat reload <gray>- Recarga la configuración");
        }
    }

    @Override
    public @Nullable List<String> onTabComplete(@NotNull CommandSender sender, @NotNull Command command, @NotNull String alias, @NotNull String[] args) {
        if (args.length != 1) {
            return List.of();
        }
        String typed = args[0].toLowerCase(Locale.ROOT);
        List<String> options = new ArrayList<>();
        if (sender.hasPermission("kickbridge.link")) options.add("link");
        if (sender.hasPermission("kickbridge.status")) options.add("status");
        if (sender.hasPermission("kickbridge.unlink")) options.add("unlink");
        if (sender.hasPermission("kickbridge.admin")) options.add("reload");

        return options.stream().filter(opt -> opt.startsWith(typed)).toList();
    }
}
