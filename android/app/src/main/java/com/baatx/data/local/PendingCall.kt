package com.baatx.data.local

import androidx.room.Dao
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Update
import kotlinx.coroutines.flow.Flow

/**
 * A call that has just ended and is waiting for the user to decide whether to
 * sync its recording with BaatX.
 *
 * This row holds call *metadata only* - number, name, duration. No audio is
 * ever captured here: the user picks the recording file themselves, and only
 * if they choose to.
 *
 * `callLogDate` is the call log's own timestamp and is unique, which stops the
 * same ended call from being queued twice when the broadcast is delivered more
 * than once.
 */
@Entity(
    tableName = "pending_calls",
    indices = [Index(value = ["callLogDate"], unique = true)],
)
data class PendingCallEntity(
    @PrimaryKey val id: String,
    val phoneNumber: String? = null,
    val contactName: String? = null,
    val direction: String = DIRECTION_UNKNOWN,
    val durationSeconds: Int = 0,
    val callLogDate: Long,
    val detectedAt: Long = System.currentTimeMillis(),
    val status: String = STATUS_PENDING,
    val jobId: String? = null,
) {
    val displayName: String
        get() = contactName?.takeIf { it.isNotBlank() }
            ?: phoneNumber?.takeIf { it.isNotBlank() }
            ?: "Unknown caller"

    companion object {
        const val STATUS_PENDING = "pending"
        const val STATUS_SYNCED = "synced"
        const val STATUS_DISMISSED = "dismissed"

        const val DIRECTION_INCOMING = "incoming"
        const val DIRECTION_OUTGOING = "outgoing"
        const val DIRECTION_UNKNOWN = "unknown"
    }
}

@Dao
interface PendingCallDao {

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(entity: PendingCallEntity): Long

    @Update
    suspend fun update(entity: PendingCallEntity)

    @Query("SELECT * FROM pending_calls WHERE id = :id")
    suspend fun byId(id: String): PendingCallEntity?

    @Query("SELECT * FROM pending_calls WHERE status = 'pending' ORDER BY callLogDate DESC")
    fun observePending(): Flow<List<PendingCallEntity>>

    @Query("SELECT COUNT(*) FROM pending_calls WHERE status = 'pending'")
    fun observePendingCount(): Flow<Int>

    @Query("SELECT COUNT(*) FROM pending_calls WHERE callLogDate = :callLogDate")
    suspend fun countForCallLogDate(callLogDate: Long): Int

    @Query("UPDATE pending_calls SET status = :status, jobId = :jobId WHERE id = :id")
    suspend fun setStatus(id: String, status: String, jobId: String? = null)

    /** Housekeeping: call metadata is not worth keeping around for long. */
    @Query("DELETE FROM pending_calls WHERE detectedAt < :olderThanEpoch")
    suspend fun purgeOlderThan(olderThanEpoch: Long)
}
