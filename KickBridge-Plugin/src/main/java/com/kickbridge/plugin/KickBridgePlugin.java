package com.kickbridge.plugin;

import com.kickbridge.plugin.api.KickBridgeApiClient;
import com.kickbridge.plugin.commands.KickChatCommand;
import com.kickbridge.plugin.config.PluginConfig;
import com.kickbridge.plugin.listeners.PlayerSessionListener;
import com.kickbridge.plugin.managers.CooldownManager;
import com.kickbridge.plugin.managers.PlayerStateManager;
import com.kickbridge.plugin.utils.MessageUtils;
import org.bukkit.command.PluginCommand;
import org.bukkit.plugin.java.JavaPlugin;

public final class KickBridgePlugin extends JavaPlugin {

    private PluginConfig pluginConfig;
    private KickBridgeApiClient apiClient;
    private PlayerStateManager stateManager;
    private CooldownManager cooldownManager;
    private MessageUtils messageUtils;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        reloadPluginState();

        PluginCommand command = getCommand("kickchat");
        if (command == null) {
            getLogger().severe("No se encontró el comando 'kickchat' en plugin.yml. Desactivando plugin.");
            getServer().getPluginManager().disablePlugin(this);
            return;
        }

        KickChatCommand executor = new KickChatCommand(this);
        command.setExecutor(executor);
        command.setTabCompleter(executor);

        getServer().getPluginManager().registerEvents(new PlayerSessionListener(this), this);
        getLogger().info("KickBridge habilitado correctamente (v" + getPluginMeta().getVersion() + ").");
    }

    @Override
    public void onDisable() {
        if (stateManager != null) {
            stateManager.clear();
        }
        if (cooldownManager != null) {
            cooldownManager.clear();
        }
        getLogger().info("KickBridge deshabilitado.");
    }

    public void reloadPluginState() {
        reloadConfig();
        this.pluginConfig = PluginConfig.fromFileConfiguration(getConfig());
        this.messageUtils = new MessageUtils(this.pluginConfig);

        if (this.stateManager == null) {
            this.stateManager = new PlayerStateManager();
        } else {
            this.stateManager.clear();
        }

        if (this.cooldownManager == null) {
            this.cooldownManager = new CooldownManager();
        }

        if (!pluginConfig.isApiUrlHttps()) {
            getLogger().warning("La URL de KickBridge API debe usar HTTPS en producción: " + pluginConfig.apiUrl());
        }
        if (pluginConfig.isDefaultToken()) {
            getLogger().warning("El token de KickBridge API sigue con el valor de ejemplo. Configura kickbridge.api.token.");
        }

        this.apiClient = new KickBridgeApiClient(this.pluginConfig);
    }

    public PluginConfig getPluginConfig() {
        return pluginConfig;
    }

    public KickBridgeApiClient getApiClient() {
        return apiClient;
    }

    public PlayerStateManager getStateManager() {
        return stateManager;
    }

    public CooldownManager getCooldownManager() {
        return cooldownManager;
    }

    public MessageUtils getMessageUtils() {
        return messageUtils;
    }
}
