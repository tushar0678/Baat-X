package com.baatx.core.calls

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log
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
 *
 * TEMPORARY: verbose Log.d() calls added throughout for diagnosing the
 * blank-phone-number issue. Search "CallEndReceiver" in Logcat while making a
 * real test call to see exactly what CallLogReader returns and what gets
 * written to pending_calls. Remove once the root cause is confirmed.
 */
@AndroidEntryPoint
class CallEndReceiver : BroadcastReceiver() {

    @Inject lateinit var callStateStore: CallStateStore
    @Inject lateinit var callLogReader: CallLogReader
    @Inject lateinit var pendingCallDao: PendingCallDao
    @Inject lateinit var notifier: CallSyncNotifier

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) {
            Log.d(TAG, "ignored: wrong action=${intent.action}")
            return
        }

        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE)
        if (state == null) {
            Log.d(TAG, "ignored: no EXTRA_STATE")
            return
        }
        val previous = callStateStore.lastState
        callStateStore.lastState = state
        Log.d(TAG, "phone state: previous=$previous current=$state")

        if (!callStateStore.callSyncEnabled) {
            Log.d(TAG, "ignored: call sync disabled in settings")
            return
        }

        val callEnded = previous == TelephonyManager.EXTRA_STATE_OFFHOOK &&
            state == TelephonyManager.EXTRA_STATE_IDLE
        if (!callEnded) {
            Log.d(TAG, "ignored: not an OFFHOOK->IDLE transition")
            return
        }

        Log.d(TAG, "call ended detected - starting call-log lookup")
        val callEndedAtMs = System.currentTimeMillis()

        val pendingResult = goAsync()
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            try {
                Log.d(TAG, "hasPermission=${callLogReader.hasPermission()}")

                val last = awaitFreshCallLogRow(callEndedAtMs)
                Log.d(
                    TAG,
                    "awaitFreshCallLogRow result: phoneNumber=${last?.phoneNumber} " +
                        "contactName=${last?.contactName} durationSeconds=${last?.durationSeconds} " +
                        "callLogDate=${last?.callLogDate}",
                )

                if (last != null && last.durationSeconds < MIN_DURATION_SECONDS) {
                    Log.d(TAG, "skipped: duration ${last.durationSeconds}s < ${MIN_DURATION_SECONDS}s")
                    return@launch
                }

                val callLogDate = last?.callLogDate ?: callEndedAtMs
                val existingCount = pendingCallDao.countForCallLogDate(callLogDate)
                Log.d(TAG, "existing rows for callLogDate=$callLogDate: $existingCount")
                if (existingCount > 0) {
                    Log.d(TAG, "skipped: already queued for this callLogDate")
                    return@launch
                }

                val entity = PendingCallEntity(
                    id = UUID.randomUUID().toString(),
                    phoneNumber = last?.phoneNumber,
                    contactName = last?.contactName,
                    direction = last?.direction ?: PendingCallEntity.DIRECTION_UNKNOWN,
                    durationSeconds = last?.durationSeconds ?: 0,
                    callLogDate = callLogDate,
                )
                Log.d(
                    TAG,
                    "inserting entity: id=${entity.id} phoneNumber=${entity.phoneNumber} " +
                        "contactName=${entity.contactName}",
                )

                val inserted = pendingCallDao.insert(entity)
                Log.d(TAG, "insert result rowId=$inserted")
                if (inserted == -1L) {
                    Log.d(TAG, "skipped: insert conflict (lost the race)")
                    return@launch
                }

                pendingCallDao.purgeOlderThan(System.currentTimeMillis() - RETENTION_MS)
                notifier.promptForCall(entity)
                Log.d(TAG, "notification posted for entity id=${entity.id}")
            } catch (t: Throwable) {
                Log.e(TAG, "CallEndReceiver coroutine threw", t)
            } finally {
                pendingResult.finish()
            }
        }
    }

    /**
     * Polls the call log for a row written *after* the call actually ended,
     * instead of trusting a single fixed delay.
     */
    private suspend fun awaitFreshCallLogRow(callEndedAtMs: Long): LastCall? {
        var attempt = 0
        var result: LastCall? = null

        while (attempt < MAX_POLL_ATTEMPTS) {
            delay(if (attempt == 0) INITIAL_DELAY_MS else POLL_INTERVAL_MS)
            val candidate = callLogReader.lastCall()
            Log.d(
                TAG,
                "poll attempt=$attempt candidate=" +
                    "${candidate?.phoneNumber}/${candidate?.callLogDate} " +
                    "(need >= ${callEndedAtMs - EARLY_TOLERANCE_MS})",
            )

            if (candidate == null) {
                Log.d(TAG, "lastCall() returned null - no permission or empty call log")
                return null
            }

            result = candidate
            if (candidate.callLogDate >= callEndedAtMs - EARLY_TOLERANCE_MS) {
                return candidate
            }
            attempt++
        }

        Log.d(TAG, "ran out of poll attempts, returning last seen candidate")
        return result
    }

    private companion object {
        const val TAG = "CallEndReceiver"
        const val INITIAL_DELAY_MS = 1_500L
        const val POLL_INTERVAL_MS = 800L
        const val MAX_POLL_ATTEMPTS = 6
        const val EARLY_TOLERANCE_MS = 2_000L
        const val MIN_DURATION_SECONDS = 5
        const val RETENTION_MS = 24 * 60 * 60 * 1000L
    }
}
