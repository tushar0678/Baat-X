package com.baatx.features.audio

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File

/**
 * Helpers for the "pick a recording" flow.
 *
 * BaatX only ever reads a file the user explicitly selected through the system
 * document picker. It does not browse storage and does not go looking for the
 * dialer's recording folder.
 */
object AudioPicking {

    fun displayName(context: Context, uri: Uri): String? =
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
        }

    fun sizeBytes(context: Context, uri: Uri): Long? =
        context.contentResolver.query(uri, null, null, null, null)?.use { cursor ->
            val index = cursor.getColumnIndex(OpenableColumns.SIZE)
            if (index >= 0 && cursor.moveToFirst()) cursor.getLong(index) else null
        }

    /** Copies the picked file into app-private storage; deleted once uploaded. */
    fun copyToPrivateStorage(context: Context, uri: Uri, name: String): File? = runCatching {
        val directory = File(context.filesDir, "pending_audio").apply { mkdirs() }
        val safeName = name.replace(Regex("[^A-Za-z0-9._-]"), "_").takeLast(80)
        val target = File(directory, "${System.currentTimeMillis()}_$safeName")
        context.contentResolver.openInputStream(uri)?.use { input ->
            target.outputStream().use { output -> input.copyTo(output) }
        } ?: return null
        target
    }.getOrNull()

    fun mimeTypeOf(context: Context, uri: Uri): String =
        context.contentResolver.getType(uri) ?: "audio/mpeg"
}
