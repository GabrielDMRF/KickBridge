package com.kickbridge.plugin.models;

import com.google.gson.annotations.SerializedName;

public final class PlayerStatusResponse {
    private boolean linked;

    @SerializedName("minecraft_uuid")
    private String minecraftUuid;

    @SerializedName("minecraft_username")
    private String minecraftUsername;

    @SerializedName("kick_user_id")
    private Long kickUserId;

    @SerializedName("kick_username")
    private String kickUsername;

    @SerializedName("linked_at")
    private String linkedAt;

    public boolean isLinked() {
        return linked;
    }

    public String getMinecraftUuid() {
        return minecraftUuid;
    }

    public String getMinecraftUsername() {
        return minecraftUsername;
    }

    public Long getKickUserId() {
        return kickUserId;
    }

    public String getKickUsername() {
        return kickUsername;
    }

    public String getLinkedAt() {
        return linkedAt;
    }
}
