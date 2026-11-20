package com.kickbridge.plugin.api;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.kickbridge.plugin.config.PluginConfig;
import com.kickbridge.plugin.models.ApiErrorResponse;
import com.kickbridge.plugin.models.ChatSendResponse;
import com.kickbridge.plugin.models.LinkStartResponse;
import com.kickbridge.plugin.models.PlayerStatusResponse;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;

public final class KickBridgeApiClient {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(15);

    private final PluginConfig config;
    private final HttpClient httpClient;
    private final Gson gson;

    public KickBridgeApiClient(PluginConfig config) {
        this.config = config;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        this.gson = new Gson();
    }

    public CompletableFuture<LinkStartResponse> startLink(UUID playerUuid, String minecraftUsername, int expirationSeconds) {
        JsonObject body = new JsonObject();
        body.addProperty("minecraft_username", minecraftUsername);
        body.addProperty("expiration_seconds", expirationSeconds);

        return sendJson("POST", "/v1/players/" + playerUuid + "/link", body.toString(), LinkStartResponse.class);
    }

    public CompletableFuture<PlayerStatusResponse> getPlayerStatus(UUID playerUuid) {
        return sendJson("GET", "/v1/players/" + playerUuid, null, PlayerStatusResponse.class);
    }

    public CompletableFuture<Void> unlinkPlayer(UUID playerUuid) {
        return sendJson("DELETE", "/v1/players/" + playerUuid, null, Void.class);
    }

    public CompletableFuture<ChatSendResponse> sendChat(UUID playerUuid, String content) {
        JsonObject body = new JsonObject();
        body.addProperty("content", content);

        return sendJson("POST", "/v1/players/" + playerUuid + "/chat", body.toString(), ChatSendResponse.class);
    }

    private <T> CompletableFuture<T> sendJson(String method, String path, String jsonBody, Class<T> responseType) {
        if (!config.isApiUrlHttps()) {
            return CompletableFuture.failedFuture(
                    new KickBridgeApiException(0, "https_required", "La URL de la API debe usar HTTPS.", null)
            );
        }
        if (config.isDefaultToken()) {
            return CompletableFuture.failedFuture(
                    new KickBridgeApiException(0, "unconfigured_token", "El token del streamer no está configurado.", null)
            );
        }

        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(config.apiUrl() + path))
                .timeout(REQUEST_TIMEOUT)
                .header("Authorization", "Bearer " + config.apiToken())
                .header("X-KB-Timestamp", String.valueOf(Instant.now().getEpochSecond()))
                .header("X-KB-Nonce", UUID.randomUUID().toString())
                .header("Accept", "application/json");

        if (jsonBody != null) {
            builder.header("Content-Type", "application/json; charset=utf-8");
            builder.method(method, HttpRequest.BodyPublishers.ofString(jsonBody, StandardCharsets.UTF_8));
        } else {
            builder.method(method, HttpRequest.BodyPublishers.noBody());
        }

        return httpClient.sendAsync(builder.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
                .thenApply(response -> parseResponse(response, responseType));
    }

    private <T> T parseResponse(HttpResponse<String> response, Class<T> responseType) {
        int status = response.statusCode();
        String raw = response.body();

        if (status >= 200 && status < 300) {
            if (responseType == Void.class || raw == null || raw.isBlank()) {
                return null;
            }
            return gson.fromJson(raw, responseType);
        }

        String code = "http_" + status;
        String message = "Error HTTP " + status;
        Integer retryAfter = null;

        if (raw != null && !raw.isBlank()) {
            try {
                ApiErrorResponse parsed = gson.fromJson(raw, ApiErrorResponse.class);
                if (parsed != null && parsed.getError() != null) {
                    if (parsed.getError().getCode() != null) {
                        code = parsed.getError().getCode();
                    }
                    if (parsed.getError().getMessage() != null) {
                        message = parsed.getError().getMessage();
                    }
                    retryAfter = parsed.getError().getRetryAfter();
                }
            } catch (Exception ignored) {
            }
        }

        if (retryAfter == null) {
            retryAfter = response.headers().firstValue("Retry-After").map(val -> {
                try {
                    return Integer.parseInt(val.trim());
                } catch (NumberFormatException ignored) {
                    return null;
                }
            }).orElse(null);
        }

        throw new KickBridgeApiException(status, code, message, retryAfter);
    }
}
