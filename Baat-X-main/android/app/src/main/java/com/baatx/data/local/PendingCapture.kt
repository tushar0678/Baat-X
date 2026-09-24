package com.baatx.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

/**
 * A capture the user made while offline (or that failed to upload).
 * Nothing is ever lost to a flaky network: the row stays here until the server
 * has accepted it, then the local audio file is deleted.
 *
 * `phoneHint`/`nameHint` carry the contact of the call this recording belongs
 * to, so a queued upload still lands on the right CRM record days later.
 */
@Entity(tableName = "pending_captures", indices = [Index(value = ["idempotencyKey"], unique = true)])
data class PendingCaptureEntity(
    @PrimaryKey val id: String,
    val idempotencyKey: String,
    val kind: String,                 // tell_ai | import_audio | import_call_recording
    val text: String? = null,
    val localAudioPath: String? = null,
    val mimeType: String? = null,
    val customerId: String? = null,
    val phoneHint: String? = null,
    val nameHint: String? = null,
    val createdAt: Long = System.currentTimeMillis(),
    val attempts: Int = 0,
    val status: String = STATUS_WAITING,
    val jobId: String? = null,
    val lastError: String? = null,
) {
    companion object {
        const val STATUS_WAITING = "waiting_for_internet"
        const val STATUS_UPLOADING = "uploading"
        const val STATUS_SUBMITTED = "submitted"
        const val STATUS_FAILED = "failed"
    }
}

@Dao
interface PendingCaptureDao {

    @Query("SELECT * FROM pending_captures WHERE status != 'submitted' ORDER BY createdAt ASC")
    fun observePending(): Flow<List<PendingCaptureEntity>>

    @Query("SELECT * FROM pending_captures WHERE status != 'submitted' ORDER BY createdAt ASC LIMIT 20")
    suspend fun pendingBatch(): List<PendingCaptureEntity>

    @Query("SELECT COUNT(*) FROM pending_captures WHERE status != 'submitted'")
    fun observePendingCount(): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insert(entity: PendingCaptureEntity)

    @Update
    suspend fun update(entity: PendingCaptureEntity)

    @Query("DELETE FROM pending_captures WHERE id = :id")
    suspend fun delete(id: String)
}

@Entity(tableName = "cached_followups")
data class CachedFollowUpEntity(
    @PrimaryKey val id: String,
    val customerName: String?,
    val title: String,
    val dueAtEpoch: Long,
    val bucket: String,               // today | tomorrow | upcoming | overdue
    val isOverdue: Boolean,
)

@Dao
interface CachedFollowUpDao {

    @Query("SELECT * FROM cached_followups ORDER BY dueAtEpoch ASC")
    fun observeAll(): Flow<List<CachedFollowUpEntity>>

    @Transaction
    suspend fun replaceAll(items: List<CachedFollowUpEntity>) {
        clear()
        insertAll(items)
    }

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(items: List<CachedFollowUpEntity>)

    @Query("DELETE FROM cached_followups")
    suspend fun clear()
}

@Database(
    entities = [
        PendingCaptureEntity::class,
        CachedFollowUpEntity::class,
        PendingCallEntity::class,
    ],
    version = 2,
    exportSchema = true,
)
abstract class BaatXDatabase : RoomDatabase() {
    abstract fun pendingCaptureDao(): PendingCaptureDao
    abstract fun cachedFollowUpDao(): CachedFollowUpDao
    abstract fun pendingCallDao(): PendingCallDao
}
