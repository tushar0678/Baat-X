package com.baatx

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import com.baatx.core.org.OrgContext
import com.baatx.data.local.BaatXDatabase
import com.baatx.work.SyncScheduler
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

@HiltAndroidApp
class BaatXApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory
    @Inject lateinit var syncScheduler: SyncScheduler
    @Inject lateinit var orgContext: OrgContext
    @Inject lateinit var database: BaatXDatabase

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()

    override fun onCreate() {
        super.onCreate()
        createNotificationChannels()

        // Anything captured offline is retried as soon as connectivity returns.
        syncScheduler.schedulePeriodicSync()

        clearCachedDataOnOrgSwitch()
    }

    /**
     * Nothing from the previous organization may survive a switch.
     *
     * The server already refuses cross-tenant requests, but a stale local
     * cache would still *display* the old organization's customers and
     * follow-ups until the next refresh - which looks exactly like a leak to
     * the person holding the phone.
     */
    private fun clearCachedDataOnOrgSwitch() {
        orgContext.addSwitchListener {
            appScope.launch {
                database.clearAllTables()
            }
        }
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
