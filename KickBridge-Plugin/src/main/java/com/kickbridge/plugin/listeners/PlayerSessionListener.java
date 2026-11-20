package com.kickbridge.plugin.listeners;

import com.kickbridge.plugin.KickBridgePlugin;
import org.bukkit.entity.Player;
import org.bukkit.event.EventHandler;
import org.bukkit.event.Listener;
import org.bukkit.event.player.PlayerJoinEvent;
import org.bukkit.event.player.PlayerQuitEvent;

import java.util.UUID;

public final class PlayerSessionListener implements Listener {
    private final KickBridgePlugin plugin;

    public PlayerSessionListener(KickBridgePlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onJoin(PlayerJoinEvent event) {
        Player player = event.getPlayer();
        UUID uuid = player.getUniqueId();

        plugin.getApiClient().getPlayerStatus(uuid)
                .thenAccept(status -> plugin.getStateManager().updateFromStatus(uuid, status))
                .exceptionally(ex -> null);
    }

    @EventHandler
    public void onQuit(PlayerQuitEvent event) {
        plugin.getStateManager().evict(event.getPlayer().getUniqueId());
    }
}
