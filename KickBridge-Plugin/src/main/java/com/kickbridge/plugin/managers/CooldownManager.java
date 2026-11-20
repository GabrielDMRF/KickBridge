package com.kickbridge.plugin.managers;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

public final class CooldownManager {
    private final Map<UUID, Instant> readyAt = new ConcurrentHashMap<>();

    public long getRemainingSeconds(UUID uuid) {
        Instant target = readyAt.get(uuid);
        if (target == null) {
            return 0L;
        }
        long millisLeft = target.toEpochMilli() - Instant.now().toEpochMilli();
        if (millisLeft <= 0) {
            readyAt.remove(uuid, target);
            return 0L;
        }
        return (millisLeft + 999L) / 1000L;
    }

    public void applyCooldown(UUID uuid, int seconds) {
        if (seconds <= 0) {
            return;
        }
        Instant next = Instant.now().plusSeconds(seconds);
        readyAt.merge(uuid, next, (existing, candidate) -> existing.isAfter(candidate) ? existing : candidate);
    }

    public void clear() {
        readyAt.clear();
    }
}
