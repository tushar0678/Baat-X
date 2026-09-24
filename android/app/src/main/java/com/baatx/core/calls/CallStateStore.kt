package com.baatx.core.calls

import android.content.Context
import androidx.core.content.edit
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Remembers the previous telephony state across broadcasts.
 *
 * A BroadcastReceiver process can be torn down between two PHONE_STATE events,
 * so this cannot live in memory: without it we could never tell "call ended"
 * (OFFHOOK -> IDLE) apart from "missed call" (RINGING -> IDLE).
 */
@Singleton
class CallStateStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs = context.getSharedPreferences("baatx_call_state", Context.MODE_PRIVATE)

    var lastState: String?
        get() = prefs.getString(KEY_LAST_STATE, null)
        set(value) = prefs.edit { putString(KEY_LAST_STATE, value) }

    /** User-controlled master switch for the whole call-sync feature. */
    var callSyncEnabled: Boolean
        get() = prefs.getBoolean(KEY_ENABLED, false)
        set(value) = prefs.edit { putBoolean(KEY_ENABLED, value) }

    private companion object {
        const val KEY_LAST_STATE = "last_state"
        const val KEY_ENABLED = "call_sync_enabled"
    }
}
