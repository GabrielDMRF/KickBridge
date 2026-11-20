package com.kickbridge.plugin.models;

import com.google.gson.annotations.SerializedName;

public final class LinkStartResponse {
    private String url;

    @SerializedName("expires_in")
    private int expiresIn;

    public String getUrl() {
        return url;
    }

    public int getExpiresIn() {
        return expiresIn;
    }
}
