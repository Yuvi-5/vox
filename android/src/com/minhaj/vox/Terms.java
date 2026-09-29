package com.minhaj.vox;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Reads the dictionary text (one entry per line, "wrong => right" for replacements). Same rules as
 * dictionary_terms and replacements in windows/vox_core.py; spec/golden.txt keeps the two in step.
 */
final class Terms {
    private Terms() { }

    /** Names and terms the speech and cleanup models should spell correctly, without duplicates. */
    static List<String> terms(String peopleRaw, String dictionaryRaw) {
        List<String> out = new ArrayList<>();
        for (String line : peopleRaw.split("\n")) {
            String l = line.trim();
            if (!l.isEmpty() && !l.startsWith("#")) add(out, l);
        }
        for (String line : dictionaryRaw.split("\n")) {
            String l = line.trim();
            if (l.isEmpty() || l.startsWith("#")) continue;
            if (l.contains("=>")) {
                String right = l.substring(l.indexOf("=>") + 2).trim();
                if (!right.isEmpty()) add(out, right);
            } else {
                add(out, l);
            }
        }
        return out;
    }

    /** Forced replacements from lines of the form "wrong => right". A later line for the same word wins. */
    static Map<String, String> replacements(String dictionaryRaw) {
        Map<String, String> out = new LinkedHashMap<>();
        for (String line : dictionaryRaw.split("\n")) {
            String l = line.trim();
            if (l.startsWith("#") || !l.contains("=>")) continue;
            String wrong = l.substring(0, l.indexOf("=>")).trim();
            String right = l.substring(l.indexOf("=>") + 2).trim();
            if (!wrong.isEmpty()) out.put(wrong, right);
        }
        return out;
    }

    private static void add(List<String> out, String term) {
        if (!out.contains(term)) out.add(term);
    }
}
