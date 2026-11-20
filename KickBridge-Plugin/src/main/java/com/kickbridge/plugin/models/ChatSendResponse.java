package com.kickbridge.plugin.models;

import com.google.gson.annotations.SerializedName;

public final class ChatSendResponse {
    private boolean sent;

    @SerializedName("message_id")
    private String messageId;

    public boolean isSent() {
        return sent;
    }

    public String getMessageId() {
        return messageId;
    }
}
