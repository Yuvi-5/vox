package com.minhaj.vox;

import java.io.IOException;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Plain-Java checks for the pure helpers in GroqClient (no Android device, no JUnit needed).
 * Run by CI: see .github/workflows/build.yml. Exits non-zero on the first failure.
 */
public final class GroqClientTest {
    private static int checks;

    private static void eq(String name, Object expected, Object actual) {
        checks++;
        if (expected == null ? actual != null : !expected.equals(actual)) {
            System.err.println("FAIL " + name + ": expected <" + expected + "> but got <" + actual + ">");
            System.exit(1);
        }
    }

    public static void main(String[] args) {
        // sanitize
        eq("sanitize strips think block", "Hello there", GroqClient.sanitize("<think>hmm\nplan</think>Hello there"));
        eq("sanitize strips transcript tags", "Hi", GroqClient.sanitize("<transcript>Hi</transcript>"));
        eq("sanitize strips wrapping quotes", "Hi there", GroqClient.sanitize("\"Hi there\""));
        eq("sanitize keeps inner quotes", "He said \"hi\" and left", GroqClient.sanitize("He said \"hi\" and left"));
        eq("sanitize null", "", GroqClient.sanitize(null));

        // looksValid
        eq("looksValid empty", false, GroqClient.looksValid("hello world", "  "));
        eq("looksValid null", false, GroqClient.looksValid("hello world", null));
        eq("looksValid normal", true, GroqClient.looksValid("hello world", "Hello, world."));
        eq("looksValid runaway reply", false, GroqClient.looksValid("hi", new String(new char[500]).replace('\0', 'x')));

        // applyReplacements: whole word, case-insensitive
        Map<String, String> repl = new LinkedHashMap<>();
        repl.put("vox", "Vox");
        eq("replace whole word", "Vox is here", GroqClient.applyReplacements("vox is here", repl));
        eq("replace ignores case", "Vox", GroqClient.applyReplacements("VOX", repl));
        eq("replace not inside a word", "voxel", GroqClient.applyReplacements("voxel", repl));
        Map<String, String> money = new LinkedHashMap<>();
        money.put("a.b", "X");
        eq("replace key is literal, not a regex", "aXb X", GroqClient.applyReplacements("aXb a.b", money));
        eq("replace empty map", "same", GroqClient.applyReplacements("same", Collections.<String, String>emptyMap()));

        // whisperPrompt
        eq("whisperPrompt empty", "", GroqClient.whisperPrompt(Collections.<String>emptyList()));
        eq("whisperPrompt null", "", GroqClient.whisperPrompt(null));
        eq("whisperPrompt joins", "Ada, Grace.", GroqClient.whisperPrompt(Arrays.asList("Ada", "Grace")));
        StringBuilder many = new StringBuilder();
        String[] terms = new String[200];
        for (int i = 0; i < terms.length; i++) terms[i] = "term" + i;
        many.append(GroqClient.whisperPrompt(Arrays.asList(terms)));
        eq("whisperPrompt stays short", true, many.length() <= 610);

        // systemPrompt
        String sp = GroqClient.systemPrompt("formal", Arrays.asList("Kubernetes"), "Slack");
        eq("systemPrompt has transcript rule", true, sp.contains("<transcript>"));
        eq("systemPrompt lists terms", true, sp.contains("Kubernetes"));
        eq("systemPrompt names the app", true, sp.contains("Slack"));
        eq("systemPrompt formal style", true, sp.contains("formal."));
        eq("systemPrompt default style", true, GroqClient.systemPrompt("nonsense", null, "").contains("neutral."));
        eq("systemPrompt no app line", false, GroqClient.systemPrompt("casual", null, "").contains("typed into the app"));

        // silence hallucinations
        eq("silence: thank you", true, GroqClient.isSilenceHallucination("Thank you."));
        eq("silence: thanks for watching", true, GroqClient.isSilenceHallucination("Thanks for watching!"));
        eq("silence: real sentence", false, GroqClient.isSilenceHallucination("Thank you for the update on Friday"));

        // retry policy
        eq("retry 500", true, GroqClient.isRetryable(new GroqClient.ApiException(500, "x")));
        eq("retry 503", true, GroqClient.isRetryable(new GroqClient.ApiException(503, "x")));
        eq("retry 429", true, GroqClient.isRetryable(new GroqClient.ApiException(429, "x")));
        eq("retry 408", true, GroqClient.isRetryable(new GroqClient.ApiException(408, "x")));
        eq("no retry 401", false, GroqClient.isRetryable(new GroqClient.ApiException(401, "x")));
        eq("no retry 400", false, GroqClient.isRetryable(new GroqClient.ApiException(400, "x")));
        eq("retry dropped connection", true, GroqClient.isRetryable(new IOException("reset")));

        System.out.println("OK: " + checks + " checks passed");
    }
}
