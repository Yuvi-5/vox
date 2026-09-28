package com.minhaj.vox;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Bundle;
import android.widget.Toast;

/** Invisible activity that starts the mic service from the foreground, then closes. */
public class TrampolineActivity extends Activity {
    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Toast.makeText(this, "Open Vox and allow the microphone", Toast.LENGTH_LONG).show();
            startActivity(new Intent(this, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } else {
            startForegroundService(new Intent(this, DictationService.class));
        }
        // Stay visible briefly so the service reaches the foreground while this activity is on screen.
        getWindow().getDecorView().postDelayed(() -> {
            finish();
            overridePendingTransition(0, 0);
        }, 400);
    }
}
