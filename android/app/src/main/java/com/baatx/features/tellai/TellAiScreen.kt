package com.baatx.features.tellai

import android.Manifest
import android.content.Context
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AudioFile
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.features.audio.SupportedAudio
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TellAiScreen(
    onBack: () -> Unit,
    onJobStarted: (String) -> Unit,
    viewModel: TellAiViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current
    var unsupportedFile by remember { mutableStateOf(false) }

    LaunchedEffect(state.startedJobId) {
        state.startedJobId?.let {
            viewModel.consumeNavigation()
            onJobStarted(it)
        }
    }

    val micPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) viewModel.startRecording() }

    // Only files the user explicitly picks are ever read.
    val filePicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val name = context.displayName(uri)
        if (!SupportedAudio.isSupported(name)) {
            unsupportedFile = true
            return@rememberLauncherForActivityResult
        }
        val copied = context.copyToCache(uri, name ?: "import.m4a")
        if (copied == null) {
            unsupportedFile = true
        } else {
            viewModel.submitImportedAudio(
                copied.absolutePath,
                context.contentResolver.getType(uri) ?: "audio/mpeg",
                isCallRecording = name?.contains("call", ignoreCase = true) == true,
            )
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Tell AI") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                "What happened with your customer?",
                style = MaterialTheme.typography.titleLarge,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                "Speak naturally in Hindi, English or Hinglish.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )

            Spacer(Modifier.height(32.dp))

            LargeFloatingActionButton(
                onClick = {
                    if (state.isRecording) {
                        viewModel.stopAndSubmitRecording()
                    } else {
                        micPermission.launch(Manifest.permission.RECORD_AUDIO)
                    }
                },
                containerColor = if (state.isRecording) {
                    MaterialTheme.colorScheme.error
                } else {
                    MaterialTheme.colorScheme.primary
                },
            ) {
                Icon(
                    if (state.isRecording) Icons.Default.Stop else Icons.Default.Mic,
                    contentDescription = if (state.isRecording) "Stop" else "Record",
                    modifier = Modifier.size(36.dp),
                )
            }
            Spacer(Modifier.height(12.dp))
            Text(
                if (state.isRecording) "Listening… tap to finish" else "Tap to start speaking",
                style = MaterialTheme.typography.bodyMedium,
            )

            Spacer(Modifier.height(28.dp))
            HorizontalDivider()
            Spacer(Modifier.height(20.dp))

            OutlinedTextField(
                value = state.text,
                onValueChange = viewModel::onTextChange,
                label = { Text("Or type what happened") },
                placeholder = {
                    Text("Aaj Rajesh se baat hui. Noida mein 2BHK chahiye, 70 lakh budget…")
                },
                minLines = 4,
                modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(12.dp))
            Button(
                onClick = viewModel::submitText,
                enabled = !state.isSubmitting && state.text.isNotBlank(),
                modifier = Modifier.fillMaxWidth().height(50.dp),
            ) {
                if (state.isSubmitting) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                } else {
                    Text("Send to BaatX")
                }
            }

            Spacer(Modifier.height(12.dp))
            OutlinedButton(
                onClick = { filePicker.launch(SupportedAudio.MIME_TYPES) },
                enabled = !state.isSubmitting,
                modifier = Modifier.fillMaxWidth().height(50.dp),
            ) {
                Icon(Icons.Default.AudioFile, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Import call recording or audio")
            }

            if (state.queuedOffline) {
                Spacer(Modifier.height(16.dp))
                AssistChip(
                    onClick = {},
                    label = { Text("Waiting for internet — we'll upload this automatically") },
                )
            }

            val message = state.error ?: if (unsupportedFile) {
                "This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG."
            } else {
                null
            }
            if (message != null) {
                Spacer(Modifier.height(16.dp))
                Text(
                    message,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    textAlign = TextAlign.Center,
                )
            }

            Spacer(Modifier.weight(1f))
            Text(
                "We don't store your recordings. We extract what matters and update your CRM.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
            )
        }
    }
}

private fun Context.displayName(uri: android.net.Uri): String? =
    contentResolver.query(uri, null, null, null, null)?.use { cursor ->
        val index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        if (index >= 0 && cursor.moveToFirst()) cursor.getString(index) else null
    }

/** Copies the picked file into app-private storage; deleted once uploaded. */
private fun Context.copyToCache(uri: android.net.Uri, name: String): File? = runCatching {
    val directory = File(filesDir, "pending_audio").apply { mkdirs() }
    val target = File(directory, "${System.currentTimeMillis()}_$name")
    contentResolver.openInputStream(uri)?.use { input ->
        target.outputStream().use { output -> input.copyTo(output) }
    } ?: return null
    target
}.getOrNull()
