package com.baatx

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.baatx.work.SyncScheduler
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class BaatXApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory
    @Inject lateinit var syncScheduler: SyncScheduler

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()
        // Anything captured offline is retried as soon as connectivity returns.
        syncScheduler.schedulePeriodicSync()
    }

    private fun createNotificationChannels() {
        val manager = getSystemService(NotificationManager::class.java)

        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_REMINDERS,
                "Follow-up reminders",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply { description = "Reminders for calls, quotations and meetings" },
        )

        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_PROCESSING,
                "Conversation processing",
                NotificationManager.IMPORTANCE_LOW,
            ).apply { description = "Progress while BaatX understands your conversation" },
        )

        // Time-sensitive: it appears right after a call ends, which is the only
        // moment the user still remembers what was discussed.
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_CALL_SYNC,
                "Call sync",
                NotificationManager.IMPORTANCE_HIGH,
            ).apply {
                description = "Offers to sync a call recording right after the call ends"
            },
        )
    }

    companion object {
        const val CHANNEL_REMINDERS = "baatx_reminders"
        const val CHANNEL_PROCESSING = "baatx_processing"
        const val CHANNEL_CALL_SYNC = "baatx_call_sync"
    }
}
