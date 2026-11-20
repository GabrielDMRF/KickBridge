package com.kickbridge.plugin.api;

public final class KickBridgeApiException extends RuntimeException {
    private final int httpStatus;
    private final String errorCode;
    private final Integer retryAfter;

    public KickBridgeApiException(int httpStatus, String errorCode, String message, Integer retryAfter) {
        super(message);
        this.httpStatus = httpStatus;
        this.errorCode = errorCode;
        this.retryAfter = retryAfter;
    }

    public int getHttpStatus() {
        return httpStatus;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public Integer getRetryAfter() {
        return retryAfter;
    }
}
