package com.baatx.core.calls

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.CallLog
import androidx.core.content.ContextCompat
import com.baatx.data.local.PendingCallEntity
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** The bare facts about the call that just finished. */
data class LastCall(
    val phoneNumber: String?,
    val contactName: String?,
    val direction: String,
    val durationSeconds: Int,
    val callLogDate: Long,
)

/**
 * Reads only the single most recent call log row, and only to pre-fill the
 * "who was this call with?" question. BaatX never scans call history.
 *
 * Returns null when the permission is not granted - the UI then simply asks
 * the user for the number instead.
 */
@Singleton
class CallLogReader @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    fun hasPermission(): Boolean = ContextCompat.checkSelfPermission(
        context,
        Manifest.permission.READ_CALL_LOG,
    ) == PackageManager.PERMISSION_GRANTED

    fun lastCall(): LastCall? {
        if (!hasPermission()) return null

        val projection = arrayOf(
            CallLog.Calls.NUMBER,
            CallLog.Calls.CACHED_NAME,
            CallLog.Calls.TYPE,
            CallLog.Calls.DURATION,
            CallLog.Calls.DATE,
        )

        return runCatching {
            context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                projection,
                null,
                null,
                "${CallLog.Calls.DATE} DESC LIMIT 1",
            )?.use { cursor ->
                if (!cursor.moveToFirst()) return@use null

                val number = cursor.getStringOrNull(CallLog.Calls.NUMBER)
                val name = cursor.getStringOrNull(CallLog.Calls.CACHED_NAME)
                val type = cursor.getIntOrNull(CallLog.Calls.TYPE) ?: 0
                val duration = cursor.getIntOrNull(CallLog.Calls.DURATION) ?: 0
                val date = cursor.getLongOrNull(CallLog.Calls.DATE) ?: 0L

                LastCall(
                    phoneNumber = number?.takeIf { it.isNotBlank() },
                    contactName = name?.takeIf { it.isNotBlank() },
                    direction = when (type) {
                        CallLog.Calls.INCOMING_TYPE -> PendingCallEntity.DIRECTION_INCOMING
                        CallLog.Calls.OUTGOING_TYPE -> PendingCallEntity.DIRECTION_OUTGOING
                        else -> PendingCallEntity.DIRECTION_UNKNOWN
                    },
                    durationSeconds = duration,
                    callLogDate = date,
                )
            }
        }.getOrNull()
    }
}

private fun android.database.Cursor.getStringOrNull(column: String): String? {
    val index = getColumnIndex(column)
    return if (index >= 0 && !isNull(index)) getString(index) else null
}

private fun android.database.Cursor.getIntOrNull(column: String): Int? {
    val index = getColumnIndex(column)
    return if (index >= 0 && !isNull(index)) getInt(index) else null
}

private fun android.database.Cursor.getLongOrNull(column: String): Long? {
    val index = getColumnIndex(column)
    return if (index >= 0 && !isNull(index)) getLong(index) else null
}
