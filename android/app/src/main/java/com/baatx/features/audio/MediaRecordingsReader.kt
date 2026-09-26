package com.baatx.features.audio

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.provider.MediaStore
import androidx.core.content.ContextCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/** One audio file found on the device, ready to be shown for the user to pick. */
data class DeviceRecording(
    val uri: Uri,
    val displayName: String,
    val sizeBytes: Long,
    val durationMs: Long,
    val dateAddedMs: Long,
    /** True when the file's storage path looks like a call-recorder folder (§ heuristic below). */
    val looksLikeCallRecording: Boolean,
)

/**
 * Reads audio files directly from MediaStore instead of relying on the system
 * document picker (Storage Access Framework).
 *
 * This exists because Samsung's own Call Recorder saves to
 * `Recordings/Call/`, a folder One UI does not expose through SAF's document
 * picker at all - the folder (and sometimes `Recordings/` itself) simply does
 * not appear as a browsable location, on any Samsung device tested, on any
 * recent One UI version. MediaStore has no such restriction: Samsung's own
 * media scanner indexes that folder like any other, so querying
 * MediaStore.Audio.Media directly reaches recordings SAF cannot.
 *
 * Read-only. BaatX never writes to or deletes from the user's media library
 * through this reader - files are only ever copied *from* here into the app's
 * private storage after the user explicitly selects one.
 */
@Singleton
class MediaRecordingsReader @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    /** The exact runtime permission this reader needs on the current OS version. */
    val requiredPermission: String
        get() = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            Manifest.permission.READ_MEDIA_AUDIO
        } else {
            Manifest.permission.READ_EXTERNAL_STORAGE
        }

    fun hasPermission(): Boolean =
        ContextCompat.checkSelfPermission(context, requiredPermission) ==
            PackageManager.PERMISSION_GRANTED

    /**
     * The most recent audio files on the device, call recordings surfaced
     * first. Returns an empty list (never throws) when permission is
     * missing or the query fails - the caller falls back to the document
     * picker either way.
     */
    fun recentRecordings(limit: Int = 30): List<DeviceRecording> {
        if (!hasPermission()) return emptyList()

        val collection = MediaStore.Audio.Media.EXTERNAL_CONTENT_URI
        val projection = arrayOf(
            MediaStore.Audio.Media._ID,
            MediaStore.Audio.Media.DISPLAY_NAME,
            MediaStore.Audio.Media.SIZE,
            MediaStore.Audio.Media.DURATION,
            MediaStore.Audio.Media.DATE_ADDED,
            MediaStore.Audio.Media.RELATIVE_PATH,
        )

        return runCatching {
            val results = mutableListOf<DeviceRecording>()
            context.contentResolver.query(
                collection,
                projection,
                null,
                null,
                "${MediaStore.Audio.Media.DATE_ADDED} DESC",
            )?.use { cursor ->
                val idCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
                val nameCol = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME)
                val sizeCol = cursor.getColumnIndex(MediaStore.Audio.Media.SIZE)
                val durationCol = cursor.getColumnIndex(MediaStore.Audio.Media.DURATION)
                val dateCol = cursor.getColumnIndex(MediaStore.Audio.Media.DATE_ADDED)
                val pathCol = cursor.getColumnIndex(MediaStore.Audio.Media.RELATIVE_PATH)

                while (cursor.moveToNext() && results.size < limit) {
                    val id = cursor.getLong(idCol)
                    val name = cursor.getString(nameCol) ?: continue
                    val relativePath = if (pathCol >= 0) cursor.getString(pathCol) else null

                    if (!SupportedAudio.isSupported(name)) continue

                    val uri = android.content.ContentUris.withAppendedId(collection, id)
                    results += DeviceRecording(
                        uri = uri,
                        displayName = name,
                        sizeBytes = if (sizeCol >= 0) cursor.getLong(sizeCol) else 0L,
                        durationMs = if (durationCol >= 0) cursor.getLong(durationCol) else 0L,
                        dateAddedMs = (if (dateCol >= 0) cursor.getLong(dateCol) else 0L) * 1000,
                        looksLikeCallRecording = isCallRecordingPath(relativePath),
                    )
                }
            }

            // Call recordings first (most relevant for this screen), each
            // group newest-first - DATE_ADDED DESC in the query already
            // ordered within each group.
            results.sortedByDescending { it.looksLikeCallRecording }
        }.getOrDefault(emptyList())
    }

    /**
     * Matches the folder layout used by Samsung, Xiaomi/MIUI, OPPO/ColorOS,
     * vivo/FuntouchOS and stock Android's own Recorder app - all of which
     * save under a "Call" or "CallRecordings" segment somewhere in the path.
     * Purely a UI heuristic (which entries to surface first); it never
     * excludes a file from the list.
     */
    private fun isCallRecordingPath(relativePath: String?): Boolean {
        val path = relativePath?.lowercase() ?: return false
        return "call" in path || "callrecording" in path
    }
}
