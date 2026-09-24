package com.baatx.features.audio

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Records only while the user is actively on the Tell AI screen.
 *
 * Uses the standard MediaRecorder MIC source - there is no call capture, no
 * accessibility hook and no background recording anywhere in BaatX.
 */
@Singleton
class AudioRecorder @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private var recorder: MediaRecorder? = null
    private var outputFile: File? = null

    val isRecording: Boolean get() = recorder != null

    fun start(): File {
        cancel()
        val directory = File(context.filesDir, "pending_audio").apply { mkdirs() }
        val file = File(directory, "tellai_${System.currentTimeMillis()}.m4a")

        val created = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }

        created.apply {
            setAudioSource(MediaRecorder.AudioSource.MIC)
            setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            setAudioEncodingBitRate(64_000)
            setAudioSamplingRate(16_000)   // plenty for speech, small on 3G
            setOutputFile(file.absolutePath)
            prepare()
            start()
        }

        recorder = created
        outputFile = file
        return file
    }

    /** Returns the finished file, or null if the recording was too short to use. */
    fun stop(): File? {
        val current = recorder ?: return null
        runCatching { current.stop() }
        current.release()
        recorder = null

        val file = outputFile
        outputFile = null
        return when {
            file == null || !file.exists() -> null
            file.length() <= 1_024 -> { file.delete(); null }
            else -> file
        }
    }

    fun cancel() {
        runCatching { recorder?.stop() }
        recorder?.release()
        recorder = null
        outputFile?.delete()
        outputFile = null
    }
}

object SupportedAudio {
    val EXTENSIONS = setOf("mp3", "m4a", "wav", "aac", "amr", "ogg")
    val MIME_TYPES = arrayOf(
        "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/wav", "audio/x-wav",
        "audio/aac", "audio/amr", "audio/3gpp", "audio/ogg",
    )

    fun isSupported(fileName: String?): Boolean =
        fileName?.substringAfterLast('.', "")?.lowercase() in EXTENSIONS
}
