package com.baatx.work

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import com.baatx.data.local.PendingCaptureDao
import com.baatx.data.local.PendingCaptureEntity
import com.baatx.data.remote.AiApi
import com.baatx.data.remote.dto.TellAIRequest
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.io.File
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Uploads everything captured while offline.
 *
 * Each capture carries a stable idempotency key, so a retry after a half-failed
 * upload can never create a duplicate conversation on the server. Local audio is
 * deleted as soon as the server accepts it.
 *
 * The contact hints ride along with the capture, so a call synced on a dead
 * network still attaches to the right customer when it finally uploads.
 */
@HiltWorker
class CaptureSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val dao: PendingCaptureDao,
    private val api: AiApi,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val pending = dao.pendingBatch()
        if (pending.isEmpty()) return Result.success()

        var hadRetryableFailure = false

        for (capture in pending) {
            dao.update(capture.copy(status = PendingCaptureEntity.STATUS_UPLOADING))
            runCatching { submit(capture) }
                .onSuccess {
                    capture.localAudioPath?.let { File(it).delete() }
                    dao.delete(capture.id)
                }
                .onFailure {
                    val attempts = capture.attempts + 1
                    if (attempts >= MAX_ATTEMPTS) {
                        dao.update(
                            capture.copy(
                                attempts = attempts,
                                status = PendingCaptureEntity.STATUS_FAILED,
                                lastError = "Couldn't upload this recording. Please try again.",
                            ),
                        )
                    } else {
                        hadRetryableFailure = true
                        dao.update(
                            capture.copy(
                                attempts = attempts,
                                status = PendingCaptureEntity.STATUS_WAITING,
                            ),
                        )
                    }
                }
        }

        return if (hadRetryableFailure) Result.retry() else Result.success()
    }

    private suspend fun submit(capture: PendingCaptureEntity): String =
        if (capture.kind == "tell_ai") {
            api.tellAi(
                TellAIRequest(
                    text = capture.text.orEmpty(),
                    idempotencyKey = capture.idempotencyKey,
                    customerId = capture.customerId,
                    phoneHint = capture.phoneHint,
                ),
            ).jobId
        } else {
            val file = File(requireNotNull(capture.localAudioPath))
            val plain = "text/plain".toMediaTypeOrNull()
            api.processAudio(
                file = MultipartBody.Part.createFormData(
                    "file",
                    file.name,
                    file.asRequestBody(capture.mimeType?.toMediaTypeOrNull()),
                ),
                idempotencyKey = capture.idempotencyKey.toRequestBody(plain),
                source = capture.kind.toRequestBody(plain),
                customerId = capture.customerId?.toRequestBody(plain),
                phoneHint = capture.phoneHint?.takeIf { it.isNotBlank() }?.toRequestBody(plain),
                nameHint = capture.nameHint?.takeIf { it.isNotBlank() }?.toRequestBody(plain),
            ).jobId
        }

    companion object {
        const val UNIQUE_NAME = "baatx_capture_sync"
        const val PERIODIC_NAME = "baatx_capture_sync_periodic"
        private const val MAX_ATTEMPTS = 8
    }
}

@Singleton
class SyncScheduler @Inject constructor(private val workManager: WorkManager) {

    private val networkConstraint = Constraints.Builder()
        .setRequiredNetworkType(NetworkType.CONNECTED)
        .build()

    /** Fires the moment connectivity returns. */
    fun requestImmediateSync() {
        workManager.enqueueUniqueWork(
            CaptureSyncWorker.UNIQUE_NAME,
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<CaptureSyncWorker>()
                .setConstraints(networkConstraint)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build(),
        )
    }

    /** Safety net for captures that outlived the process. */
    fun schedulePeriodicSync() {
        workManager.enqueueUniquePeriodicWork(
            CaptureSyncWorker.PERIODIC_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<CaptureSyncWorker>(1, TimeUnit.HOURS)
                .setConstraints(networkConstraint)
                .build(),
        )
    }
}
