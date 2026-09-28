package com.minhaj.vox;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Foreground service of type "microphone". It must be started from a visible activity
 * (Android blocks background mic access), then it keeps running so the bubble can record any time.
 */
public class DictationService extends Service {
    public static final int SAMPLE_RATE = 16000;
    private static final int MAX_SECONDS = 360;
    private static final String CH = "vox_service";
    private static final String ACTION_STOP = "com.minhaj.vox.STOP";

    public static final int IDLE = 0, RECORDING = 1, PROCESSING = 2;

    public interface Listener {
        void onState(int s);
        void onLevel(float level);          // 0..1 while recording
        void onResult(String text, String targetPkg);
        void onError(String message);
    }

    public static volatile DictationService instance;
    private static Listener listener;

    public static void setListener(Listener l) { listener = l; }

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private volatile int state = IDLE;
    private volatile boolean recording;
    private volatile boolean cancelled;
    private Thread recThread;
    private ByteArrayOutputStream pcm;
    private String targetPkg;
    private String targetLabel;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public void onCreate() {
        super.onCreate();
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel ch = new NotificationChannel(CH, "Vox dictation", NotificationManager.IMPORTANCE_MIN);
        ch.setShowBadge(false);
        nm.createNotificationChannel(ch);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        Notification n = buildNotification();
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
        } else {
            startForeground(1, n);
        }
        instance = this;
        VoxAccessibilityService a = VoxAccessibilityService.instance;
        if (a != null) a.onDictationServiceReady();
        return START_NOT_STICKY;
    }

    private Notification buildNotification() {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent openPi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE);
        Intent stop = new Intent(this, DictationService.class).setAction(ACTION_STOP);
        PendingIntent stopPi = PendingIntent.getService(this, 1, stop, PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this, CH)
                .setSmallIcon(R.drawable.ic_stat_mic)
                .setContentTitle("Vox is ready")
                .setContentText("Tap the bubble in any text field to dictate")
                .setContentIntent(openPi)
                .addAction(new Notification.Action.Builder(null, "Turn off", stopPi).build())
                .setOngoing(true)
                .build();
    }

    @Override
    public void onDestroy() {
        recording = false;
        cancelled = true;
        instance = null;
        worker.shutdownNow();
        setState(IDLE);
        super.onDestroy();
    }

    public int getState() { return state; }

    // ------------------------------------------------------------ recording

    public synchronized void startRecording(String pkg, String label) {
        if (state != IDLE) return;
        Prefs p = new Prefs(this);
        if (p.apiKey().isEmpty()) {
            postError("Add your Groq API key in the Vox app first");
            return;
        }
        targetPkg = pkg;
        targetLabel = label;
        int minBuf = AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT);
        final AudioRecord rec;
        try {
            rec = new AudioRecord(MediaRecorder.AudioSource.VOICE_RECOGNITION, SAMPLE_RATE,
                    AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT, Math.max(minBuf, SAMPLE_RATE));
        } catch (SecurityException e) {
            postError("Microphone permission missing. Open Vox and allow it.");
            return;
        }
        if (rec.getState() != AudioRecord.STATE_INITIALIZED) {
            rec.release();
            postError("Microphone unavailable (another app may be using it)");
            return;
        }
        pcm = new ByteArrayOutputStream();
        recording = true;
        cancelled = false;
        setState(RECORDING);
        recThread = new Thread(() -> {
            byte[] buf = new byte[3200]; // 100 ms
            long maxBytes = (long) SAMPLE_RATE * 2 * MAX_SECONDS;
            try {
                rec.startRecording();
                while (recording) {
                    int n = rec.read(buf, 0, buf.length);
                    if (n <= 0) continue;
                    pcm.write(buf, 0, n);
                    postLevel(rms(buf, n));
                    if (pcm.size() >= maxBytes) {
                        main.post(this::stopRecording);
                        break;
                    }
                }
            } catch (Exception e) {
                postError("Recording failed: " + e.getMessage());
            } finally {
                try { rec.stop(); } catch (Exception ignored) { }
                rec.release();
            }
        }, "vox-rec");
        recThread.start();
    }

    /** Stops recording and sends the audio for transcription. */
    public synchronized void stopRecording() {
        if (state != RECORDING) return;
        recording = false;
        setState(PROCESSING);
        final Thread t = recThread;
        final ByteArrayOutputStream data = pcm;
        final String pkg = targetPkg;
        final String label = targetLabel;
        worker.execute(() -> {
            try { if (t != null) t.join(2000); } catch (InterruptedException ignored) { }
            if (cancelled) { setState(IDLE); return; }
            byte[] audio = data.toByteArray();
            if (audio.length < SAMPLE_RATE * 2 * 0.4) { // under 0.4 s
                setState(IDLE);
                return;
            }
            process(audio, pkg, label);
        });
    }

    /** Discards the current recording. */
    public synchronized void cancel() {
        cancelled = true;
        recording = false;
        setState(IDLE);
    }

    private void process(byte[] audio, String pkg, String label) {
        Prefs p = new Prefs(this);
        File wav = new File(getCacheDir(), "rec.wav");
        String raw = null;
        try {
            writeWav(wav, audio);
            GroqClient g = new GroqClient(p.apiKey());
            raw = g.transcribe(wav, p.sttModel(), p.language(), p.dictionaryTerms());
            if (cancelled) { setState(IDLE); return; }
            if (raw.isEmpty() || isSilenceHallucination(raw)) {
                setState(IDLE);
                return;
            }
            String style = p.styleFor(pkg);
            String out = raw;
            boolean doClean = p.cleanupEnabled() && !"raw".equals(style) && raw.split("\\s+").length >= 3;
            if (doClean) {
                try {
                    String c = g.cleanup(raw, style, p.llmModel(), p.dictionaryTerms(), label);
                    if (GroqClient.looksValid(raw, c)) out = c;
                } catch (IOException e) {
                    // Cleanup failure should never lose the dictation. Fall back to the raw transcript.
                }
            }
            out = GroqClient.applyReplacements(out, p.replacements());
            p.addHistory(label, raw, out, audio.length / (SAMPLE_RATE * 2.0));
            if (cancelled) { setState(IDLE); return; }
            final String result = out;
            main.post(() -> { if (listener != null) listener.onResult(result, pkg); });
        } catch (GroqClient.ApiException e) {
            if (e.code == 401) postError("Groq rejected the API key");
            else if (e.code == 429) postError("Groq free limit reached. Try again shortly.");
            else postError(e.getMessage());
        } catch (IOException e) {
            postError("Network error: " + e.getMessage());
        } finally {
            wav.delete();
            setState(IDLE);
        }
    }

    /** Whisper tends to invent these phrases on silence. */
    static boolean isSilenceHallucination(String t) {
        String s = t.toLowerCase().replaceAll("[^a-z ]", "").trim();
        return s.equals("thank you") || s.equals("thanks for watching") || s.equals("you")
                || s.equals("thank you for watching") || s.equals("bye");
    }

    // ------------------------------------------------------------- helpers

    private void setState(int s) {
        state = s;
        main.post(() -> { if (listener != null) listener.onState(s); });
    }

    private void postLevel(float l) { main.post(() -> { if (listener != null) listener.onLevel(l); }); }

    private void postError(String m) { main.post(() -> { if (listener != null) listener.onError(m); }); }

    private static float rms(byte[] b, int n) {
        long sum = 0;
        int samples = n / 2;
        for (int i = 0; i + 1 < n; i += 2) {
            short v = (short) ((b[i] & 0xff) | (b[i + 1] << 8));
            sum += (long) v * v;
        }
        double r = Math.sqrt(sum / (double) Math.max(1, samples)) / 32768.0;
        return (float) Math.min(1.0, r * 6);
    }

    static void writeWav(File f, byte[] pcm) throws IOException {
        int byteRate = SAMPLE_RATE * 2;
        try (FileOutputStream o = new FileOutputStream(f)) {
            o.write(new byte[]{'R', 'I', 'F', 'F'});
            le32(o, 36 + pcm.length);
            o.write(new byte[]{'W', 'A', 'V', 'E', 'f', 'm', 't', ' '});
            le32(o, 16);
            le16(o, 1);            // PCM
            le16(o, 1);            // mono
            le32(o, SAMPLE_RATE);
            le32(o, byteRate);
            le16(o, 2);            // block align
            le16(o, 16);           // bits per sample
            o.write(new byte[]{'d', 'a', 't', 'a'});
            le32(o, pcm.length);
            o.write(pcm);
        }
    }

    private static void le32(FileOutputStream o, int v) throws IOException {
        o.write(v & 0xff); o.write((v >> 8) & 0xff); o.write((v >> 16) & 0xff); o.write((v >> 24) & 0xff);
    }

    private static void le16(FileOutputStream o, int v) throws IOException {
        o.write(v & 0xff); o.write((v >> 8) & 0xff);
    }
}
