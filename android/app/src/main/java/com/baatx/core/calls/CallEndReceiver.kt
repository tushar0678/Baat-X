package com.baatx.core.calls

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import com.baatx.data.local.PendingCallDao
import com.baatx.data.local.PendingCallEntity
import dagger.hilt.android.AndroidEntryPoint
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Notices that a call has ended and offers to sync it.
 *
 * Only the OFFHOOK -> IDLE transition counts: that is a call that was actually
 * connected. RINGING -> IDLE is a missed or rejected call and is ignored, so
 * the user is never nagged about calls that never happened.
 *
 * This receiver reads call metadata only. It does not record, does not touch
 * audio, and uploads nothing - it just queues a prompt.
 */
@AndroidEntryPoint
class CallEndReceiver : BroadcastReceiver() {

    @Inject lateinit var callStateStore: CallStateStore
    @Inject lateinit var callLogReader: CallLogReader
    @Inject lateinit var pendingCallDao: PendingCallDao
    @Inject lateinit var notifier: CallSyncNotifier

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return

        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return
        val previous = callStateStore.lastState
        callStateStore.lastState = state

        if (!callStateStore.callSyncEnabled) return

        val callEnded = previous == TelephonyManager.EXTRA_STATE_OFFHOOK &&
            state == TelephonyManager.EXTRA_STATE_IDLE
        if (!callEnded) return

        val pendingResult = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                // The dialer writes its call log row a moment after the call
                // ends; reading immediately usually returns the previous call.
                delay(CALL_LOG_SETTLE_MS)

                val last = callLogReader.lastCall()

                // Too short to be a real conversation - almost always a
                // misdial or an instantly-ended call.
                if (last != null && last.durationSeconds < MIN_DURATION_SECONDS) return@launch

                val callLogDate = last?.callLogDate ?: System.currentTimeMillis()
                if (pendingCallDao.countForCallLogDate(callLogDate) > 0) return@launch

                val entity = PendingCallEntity(
                    id = UUID.randomUUID().toString(),
                    phoneNumber = last?.phoneNumber,
                    contactName = last?.contactName,
                    direction = last?.direction ?: PendingCallEntity.DIRECTION_UNKNOWN,
                    durationSeconds = last?.durationSeconds ?: 0,
                    callLogDate = callLogDate,
                )

                val inserted = pendingCallDao.insert(entity)
                if (inserted == -1L) return@launch  // lost the race, already queued

                // Keep only the last day of call metadata.
                pendingCallDao.purgeOlderThan(System.currentTimeMillis() - RETENTION_MS)

                notifier.promptForCall(entity)
            } catch (_: Throwable) {
                // A failed prompt must never crash the phone app's broadcast.
            } finally {
                pendingResult.finish()
            }
        }
    }

    private companion object {
        const val CALL_LOG_SETTLE_MS = 1_500L
        const val MIN_DURATION_SECONDS = 5
        const val RETENTION_MS = 24 * 60 * 60 * 1000L
    }
}
