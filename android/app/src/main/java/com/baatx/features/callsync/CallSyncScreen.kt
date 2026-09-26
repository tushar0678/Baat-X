package com.baatx.features.callsync

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AudioFile
import androidx.compose.material.icons.filled.CallReceived
import androidx.compose.material.icons.filled.CallMade
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.LoadingState
import com.baatx.data.local.PendingCallEntity
import com.baatx.features.audio.DeviceRecording
import com.baatx.features.audio.SupportedAudio
import java.util.concurrent.TimeUnit

/**
 * "That call just ended - sync it?"
 *
 * Everything on this screen is a confirmation: the number is editable, the
 * recording is chosen by the user, and nothing is uploaded without the consent
 * tick. BaatX never captures call audio by itself.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CallSyncScreen(
    callId: String,
    onBack: () -> Unit,
    onJobStarted: (String) -> Unit,
    viewModel: CallSyncViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val context = LocalContext.current

    LaunchedEffect(callId) { viewModel.load(callId) }
    LaunchedEffect(state.finished) { if (state.finished) onBack() }
    LaunchedEffect(state.startedJobId) {
        state.startedJobId?.let {
            viewModel.consumeNavigation()
            onJobStarted(it)
        }
    }

    val mediaPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> viewModel.onMediaPermissionResult(granted) }

    val recordingPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri -> viewModel.onDocumentPicked(context, uri) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Sync call") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        if (state.isLoading) {
            Box(Modifier.fillMaxSize().padding(padding)) { LoadingState() }
            return@Scaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            state.call?.let { CallSummaryCard(it) }

            Text("Who was this call with?", style = MaterialTheme.typography.titleMedium)

            OutlinedTextField(
                value = state.phoneNumber,
                onValueChange = viewModel::onPhoneChange,
                label = { Text("Mobile number") },
                supportingText = {
                    Text("This is what links the call to the right customer.")
                },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                modifier = Modifier.fillMaxWidth(),
            )

            OutlinedTextField(
                value = state.contactName,
                onValueChange = viewModel::onNameChange,
                label = { Text("Name (optional)") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth(),
            )

            HorizontalDivider()

            Text("Recording", style = MaterialTheme.typography.titleMedium)

            if (state.recordingName != null) {
                ListItem(
                    headlineContent = { Text(state.recordingName!!) },
                    supportingContent = { Text("Ready to upload") },
                    leadingContent = {
                        Icon(Icons.Default.AudioFile, contentDescription = null)
                    },
                    trailingContent = {
                        TextButton(onClick = viewModel::clearRecording) { Text("Change") }
                    },
                )
            } else {
                RecordingPicker(
                    state = state,
                    onRequestPermission = { mediaPermissionLauncher.launch(state.mediaPermissionRequired) },
                    onSelectDeviceRecording = viewModel::onDeviceRecordingSelected,
                    onOpenDocumentPicker = { recordingPicker.launch(SupportedAudio.MIME_TYPES) },
                )
            }

            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(
                    checked = state.consentGiven,
                    onCheckedChange = viewModel::onConsentChange,
                )
                Spacer(Modifier.width(4.dp))
                Text(
                    "I'm allowed to process this recording.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            if (state.queuedOffline) {
                AssistChip(
                    onClick = {},
                    label = { Text("Waiting for internet — we'll upload this automatically") },
                )
            }

            state.error?.let {
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            Button(
                onClick = viewModel::sync,
                enabled = state.canSync,
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                if (state.isSubmitting) {
                    CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                } else {
                    Icon(Icons.Default.Check, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Sync to BaatX")
                }
            }

            TextButton(
                onClick = viewModel::dismissCall,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Not now")
            }

            Text(
                "We don't store your recordings. We extract what matters and update your CRM.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * Recent recordings read from MediaStore, plus a fallback to the system
 * document picker.
 *
 * The MediaStore list exists because Samsung's Call Recorder saves to
 * Recordings/Call/, a folder One UI's own document picker does not expose -
 * "Choose a file" alone left Samsung users with an empty picker and no way to
 * attach the recording they clearly had. MediaStore has no such restriction.
 * The document picker stays as a fallback for recordings MediaStore hasn't
 * indexed yet, or for other apps that save call recordings differently.
 */
@Composable
private fun RecordingPicker(
    state: CallSyncUiState,
    onRequestPermission: () -> Unit,
    onSelectDeviceRecording: (DeviceRecording) -> Unit,
    onOpenDocumentPicker: () -> Unit,
) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(
            "Pick the recording of this call from your phone. BaatX can't record " +
                "calls itself, so choose the file your dialer saved.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        when {
            !state.hasMediaPermission -> {
                OutlinedButton(
                    onClick = onRequestPermission,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                ) {
                    Icon(Icons.Default.AudioFile, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Allow access to recordings")
                }
            }

            state.isLoadingRecordings -> {
                Box(Modifier.fillMaxWidth().height(80.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp)
                }
            }

            state.deviceRecordings.isNotEmpty() -> {
                Text(
                    "Recent recordings",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(state.deviceRecordings, key = { it.uri.toString() }) { recording ->
                        RecordingCard(
                            recording = recording,
                            onClick = { onSelectDeviceRecording(recording) },
                        )
                    }
                }
            }

            else -> {
                Text(
                    "No recordings found automatically. You can still browse for the file.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        OutlinedButton(
            onClick = onOpenDocumentPicker,
            modifier = Modifier.fillMaxWidth().height(50.dp),
        ) {
            Icon(Icons.Default.AudioFile, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("Browse for a file instead")
        }
    }
}

@Composable
private fun RecordingCard(recording: DeviceRecording, onClick: () -> Unit) {
    Card(
        onClick = onClick,
        colors = CardDefaults.cardColors(
            containerColor = if (recording.looksLikeCallRecording) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
        ),
        modifier = Modifier.width(180.dp),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            if (recording.looksLikeCallRecording) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        Icons.Default.Phone,
                        contentDescription = null,
                        modifier = Modifier.size(14.dp),
                        tint = MaterialTheme.colorScheme.primary,
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        "Call recording",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
            Text(
                recording.displayName,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
            )
            Text(
                formatDuration(recording.durationMs),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

private fun formatDuration(durationMs: Long): String {
    if (durationMs <= 0) return ""
    val totalSeconds = TimeUnit.MILLISECONDS.toSeconds(durationMs)
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    return if (minutes > 0) "${minutes}m ${seconds}s" else "${seconds}s"
}

@Composable
private fun CallSummaryCard(call: PendingCallEntity) {
    val minutes = call.durationSeconds / 60
    val seconds = call.durationSeconds % 60
    val duration = if (minutes > 0) "${minutes}m ${seconds}s" else "${seconds}s"

    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                if (call.direction == PendingCallEntity.DIRECTION_INCOMING) {
                    Icons.Default.CallReceived
                } else {
                    Icons.Default.CallMade
                },
                contentDescription = null,
            )
            Spacer(Modifier.width(12.dp))
            Column {
                Text(call.displayName, style = MaterialTheme.typography.titleMedium)
                Text(
                    "Call ended • $duration",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
