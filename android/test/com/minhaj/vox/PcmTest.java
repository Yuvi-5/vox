package com.minhaj.vox;

/** Plain-Java checks for the silence gate in Pcm. Run by CI, exits non-zero on failure. */
public final class PcmTest {
    private static int checks;

    private static void check(String name, boolean ok) {
        checks++;
        if (!ok) {
            System.err.println("FAIL " + name);
            System.exit(1);
        }
    }

    private static byte[] pcm(int... samples) {
        byte[] b = new byte[samples.length * 2];
        for (int i = 0; i < samples.length; i++) {
            b[2 * i] = (byte) (samples[i] & 0xff);
            b[2 * i + 1] = (byte) ((samples[i] >> 8) & 0xff);
        }
        return b;
    }

    public static void main(String[] args) {
        check("null is silent", Pcm.isSilent(null));
        check("empty is silent", Pcm.isSilent(new byte[0]));
        check("one byte is silent", Pcm.isSilent(new byte[] {1}));
        check("zeros are silent", Pcm.isSilent(pcm(0, 0, 0, 0)));
        check("low noise is silent", Pcm.isSilent(pcm(200, -300, 150, -250)));
        check("speech is not silent", !Pcm.isSilent(pcm(0, 4000, -6000, 3000, 0)));
        check("negative peak counts", !Pcm.isSilent(pcm(0, -20000, 0)));
        check("most negative sample counts", !Pcm.isSilent(pcm(0, -32768, 0)));
        check("just under threshold is silent", Pcm.isSilent(pcm(Pcm.SILENCE_PEAK - 1, -(Pcm.SILENCE_PEAK - 1))));
        check("at threshold is not silent", !Pcm.isSilent(pcm(Pcm.SILENCE_PEAK)));
        check("custom threshold", Pcm.isSilent(pcm(100), 101) && !Pcm.isSilent(pcm(101), 101));
        check("odd trailing byte ignored", Pcm.isSilent(concat(pcm(10, 20), new byte[] {(byte) 0xff})));
        System.out.println("OK: " + checks + " checks passed");
    }

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] out = new byte[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }
}
