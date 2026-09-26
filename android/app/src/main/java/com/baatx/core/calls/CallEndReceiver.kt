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

        // Captured at the moment the call actually ended, before any settle
        // delay - used below to make sure the call-log row we eventually read
        // is new, not a stale one from a previous call.
        val callEndedAtMs = System.currentTimeMillis()

        val pendingResult = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                val last = awaitFreshCallLogRow(callEndedAtMs)

                // Too short to be a real conversation - almost always a
                // misdial or an instantly-ended call.
                if (last != null && last.durationSeconds < MIN_DURATION_SECONDS) return@launch

                val callLogDate = last?.callLogDate ?: callEndedAtMs
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

    /**
     * Polls the call log for a row written *after* the call actually ended,
     * instead of trusting a single fixed delay.
     *
     * Some OEM dialers (notably Samsung and Xiaomi) take 2-4 seconds to write
     * the call log entry after the OFFHOOK -> IDLE transition - well past the
     * previous single 1.5s delay. Reading too early silently returned the
     * *previous* call's row, whose callLogDate already existed in
     * pending_calls, so countForCallLogDate() short-circuited and no new row
     * (with the correct number) was ever inserted - the notification still
     * fired from an earlier, blank-looking entry.
     *
     * A row is considered "fresh" once its callLogDate is at or after the
     * moment the call ended; on devices with clock skew between the telephony
     * broadcast and the call log provider, EARLY_TOLERANCE_MS absorbs a small
     * amount of that skew rather than polling forever.
     */
    private suspend fun awaitFreshCallLogRow(callEndedAtMs: Long): LastCall? {
        var attempt = 0
        var result: LastCall? = null

        while (attempt < MAX_POLL_ATTEMPTS) {
            delay(if (attempt == 0) INITIAL_DELAY_MS else POLL_INTERVAL_MS)
            val candidate = callLogReader.lastCall()

            if (candidate == null) {
                // No permission, or no call log at all - nothing further to
                // wait for.
                return null
            }

            result = candidate
            if (candidate.callLogDate >= callEndedAtMs - EARLY_TOLERANCE_MS) {
                return candidate
            }
            attempt++
        }

        // Ran out of attempts: return whatever we last saw rather than
        // nothing, so the user at least gets *a* prefilled number to correct,
        // instead of a blank field with no explanation.
        return result
    }

    private companion object {
        const val INITIAL_DELAY_MS = 1_500L
        const val POLL_INTERVAL_MS = 800L
        const val MAX_POLL_ATTEMPTS = 6   // ~1.5s + 6*0.8s ≈ 6.3s total ceiling
        const val EARLY_TOLERANCE_MS = 2_000L
        const val MIN_DURATION_SECONDS = 5
        const val RETENTION_MS = 24 * 60 * 60 * 1000L
    }
}
