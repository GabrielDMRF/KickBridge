package com.kickbridge.plugin.utils;

import com.kickbridge.plugin.config.PluginConfig;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickEvent;
import net.kyori.adventure.text.event.HoverEvent;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import net.kyori.adventure.text.minimessage.MiniMessage;
import net.kyori.adventure.text.minimessage.tag.resolver.Placeholder;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

public final class MessageUtils {
    private static final MiniMessage MINI = MiniMessage.miniMessage();
    private final PluginConfig config;

    public MessageUtils(PluginConfig config) {
        this.config = config;
    }

    public void sendPrefixed(CommandSender target, String miniMessageBody) {
        Component prefix = MINI.deserialize(config.prefix());
        Component body = MINI.deserialize(miniMessageBody);
        target.sendMessage(prefix.append(body));
    }

    public void sendPlainError(CommandSender target, String safeText) {
        Component prefix = MINI.deserialize(config.prefix());
        target.sendMessage(prefix.append(Component.text(safeText, NamedTextColor.RED)));
    }

    public void sendCooldown(Player player, long seconds) {
        String raw = config.msgCooldown().replace("%time%", String.valueOf(seconds));
        sendPrefixed(player, raw);
    }

    public void sendLinkPrompt(Player player, String url, int expiresInSeconds) {
        Component prefix = MINI.deserialize(config.prefix());
        Component intro = MINI.deserialize(
                "<yellow>Haz clic abajo para vincular tu cuenta de Kick (expira en <white><seconds></white>s):",
                Placeholder.unparsed("seconds", String.valueOf(expiresInSeconds))
        );
        Component button = Component.text("[Abrir autorización oficial de Kick]", NamedTextColor.GREEN, TextDecoration.BOLD)
                .clickEvent(ClickEvent.openUrl(url))
                .hoverEvent(HoverEvent.showText(Component.text("Abrir enlace HTTPS en tu navegador:\n" + url, NamedTextColor.GRAY)));

        player.sendMessage(prefix.append(intro));
        player.sendMessage(prefix.append(button));
    }

    public void sendStatusLinked(Player player, String kickUsername) {
        Component prefix = MINI.deserialize(config.prefix());
        Component body = MINI.deserialize(
                "<green>Cuenta vinculada a Kick como <white><bold><kick_user></bold></white>.",
                Placeholder.unparsed("kick_user", kickUsername != null ? kickUsername : "Desconocido")
        );
        player.sendMessage(prefix.append(body));
    }
}
