package com.kickbridge.plugin.managers;

import com.kickbridge.plugin.models.PlayerStatusResponse;

import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class PlayerStateManager {
    private final Map<UUID, CachedLinkState> cache = new ConcurrentHashMap<>();

    public void updateFromStatus(UUID uuid, PlayerStatusResponse status) {
        if (status == null || !status.isLinked()) {
            cache.put(uuid, new CachedLinkState(false, null));
            return;
        }
        cache.put(uuid, new CachedLinkState(true, status.getKickUsername()));
    }

    public void markUnlinked(UUID uuid) {
        cache.put(uuid, new CachedLinkState(false, null));
    }

    public Optional<CachedLinkState> getCached(UUID uuid) {
        return Optional.ofNullable(cache.get(uuid));
    }

    public void evict(UUID uuid) {
        cache.remove(uuid);
    }

    public void clear() {
        cache.clear();
    }

    public record CachedLinkState(boolean linked, String kickUsername) {
    }
}
