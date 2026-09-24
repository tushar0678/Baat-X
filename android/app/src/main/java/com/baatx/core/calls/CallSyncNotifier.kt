package com.baatx.core.calls

import android.Manifest
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.baatx.BaatXApplication
import com.baatx.MainActivity
import com.baatx.R
import com.baatx.data.local.PendingCallEntity
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The "call ended - sync it?" prompt.
 *
 * A notification rather than a surprise full-screen popup: the call has just
 * ended, the user may be mid-something, and Android does not let background
 * apps steal the screen. Tapping it opens the sync screen inside BaatX.
 */
@Singleton
class CallSyncNotifier @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    fun canNotify(): Boolean =
        android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED

    fun promptForCall(call: PendingCallEntity) {
        if (!canNotify()) return

        val intent = Intent(context, MainActivity::class.java).apply {
            action = MainActivity.ACTION_OPEN_CALL_SYNC
            putExtra(MainActivity.EXTRA_CALL_ID, call.id)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
        }

        val pendingIntent = PendingIntent.getActivity(
            context,
            call.id.hashCode(),
            intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )

        val minutes = call.durationSeconds / 60
        val seconds = call.durationSeconds % 60
        val duration = if (minutes > 0) "${minutes}m ${seconds}s" else "${seconds}s"

        val notification = NotificationCompat.Builder(
            context,
            BaatXApplication.CHANNEL_CALL_SYNC,
        )
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle("Sync this call with BaatX?")
            .setContentText("${call.displayName} • $duration")
            .setStyle(
                NotificationCompat.BigTextStyle().bigText(
                    "Call with ${call.displayName} ($duration) just ended. " +
                        "Tap to attach the recording and update your CRM.",
                ),
            )
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setCategory(NotificationCompat.CATEGORY_REMINDER)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)
            .addAction(0, "Sync recording", pendingIntent)
            .build()

        runCatching {
            NotificationManagerCompat.from(context).notify(call.id.hashCode(), notification)
        }
    }

    fun dismiss(callId: String) {
        NotificationManagerCompat.from(context).cancel(callId.hashCode())
    }
}
