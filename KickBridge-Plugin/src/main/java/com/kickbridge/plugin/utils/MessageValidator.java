package com.kickbridge.plugin.utils;

import java.nio.charset.StandardCharsets;
import java.text.BreakIterator;
import java.util.Locale;
import java.util.Set;

public final class MessageValidator {
    private static final int KICK_MAX_UTF8_BYTES = 2048;
    private static final Set<Integer> BIDI_CONTROLS = Set.of(
            0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2066, 0x2067, 0x2068, 0x2069
    );

    private MessageValidator() {
    }

    public static ValidationResult validate(String raw, int maxGraphemes) {
        if (raw == null) {
            return ValidationResult.invalid("El mensaje está vacío.");
        }
        String cleaned = raw.strip();
        if (cleaned.isEmpty()) {
            return ValidationResult.invalid("El mensaje está vacío.");
        }

        for (int i = 0; i < cleaned.length(); ) {
            int cp = cleaned.codePointAt(i);
            int type = Character.getType(cp);
            if (type == Character.CONTROL || type == Character.SURROGATE || type == Character.PRIVATE_USE || BIDI_CONTROLS.contains(cp)) {
                return ValidationResult.invalid("El mensaje contiene caracteres no permitidos.");
            }
            i += Character.charCount(cp);
        }

        if (graphemeLength(cleaned) > maxGraphemes) {
            return ValidationResult.invalid("El mensaje supera el máximo de " + maxGraphemes + " caracteres.");
        }
        if (cleaned.getBytes(StandardCharsets.UTF_8).length > KICK_MAX_UTF8_BYTES) {
            return ValidationResult.invalid("El mensaje supera el tamaño permitido por Kick.");
        }
        return ValidationResult.valid(cleaned);
    }

    private static int graphemeLength(String text) {
        BreakIterator it = BreakIterator.getCharacterInstance(Locale.ROOT);
        it.setText(text);
        int count = 0;
        while (it.next() != BreakIterator.DONE) {
            count++;
        }
        return count;
    }

    public record ValidationResult(boolean valid, String sanitized, String reason) {
        static ValidationResult valid(String sanitized) {
            return new ValidationResult(true, sanitized, null);
        }

        static ValidationResult invalid(String reason) {
            return new ValidationResult(false, null, reason);
        }
    }
}
