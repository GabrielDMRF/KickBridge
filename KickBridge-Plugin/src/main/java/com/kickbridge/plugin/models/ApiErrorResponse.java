package com.kickbridge.plugin.models;

import com.google.gson.annotations.SerializedName;

public final class ApiErrorResponse {
    private ErrorDetail error;

    public ErrorDetail getError() {
        return error;
    }

    public static final class ErrorDetail {
        private String code;
        private String message;

        @SerializedName("retry_after")
        private Integer retryAfter;

        @SerializedName("kick_status")
        private Integer kickStatus;

        public String getCode() {
            return code;
        }

        public String getMessage() {
            return message;
        }

        public Integer getRetryAfter() {
            return retryAfter;
        }

        public Integer getKickStatus() {
            return kickStatus;
        }
    }
}
