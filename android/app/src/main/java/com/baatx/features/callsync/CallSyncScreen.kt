package com.baatx.features.callsync

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AudioFile
import androidx.compose.material.icons.filled.CallReceived
import androidx.compose.material.icons.filled.CallMade
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.LoadingState
import com.baatx.data.local.PendingCallEntity
import com.baatx.features.audio.AudioPicking
import com.baatx.features.audio.SupportedAudio

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

    val recordingPicker = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument(),
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        val name = AudioPicking.displayName(context, uri)
        if (!SupportedAudio.isSupported(name)) {
            viewModel.onPickFailed()
            return@rememberLauncherForActivityResult
        }
        val copied = AudioPicking.copyToPrivateStorage(context, uri, name ?: "call.m4a")
        if (copied == null) {
            viewModel.onPickFailed()
        } else {
            viewModel.onRecordingPicked(
                path = copied.absolutePath,
                mimeType = AudioPicking.mimeTypeOf(context, uri),
                displayName = name,
            )
        }
    }

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

            if (state.recordingName == null) {
                Text(
                    "Pick the recording of this call from your phone. BaatX can't record " +
                        "calls itself, so choose the file your dialer saved.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                OutlinedButton(
                    onClick = { recordingPicker.launch(SupportedAudio.MIME_TYPES) },
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                ) {
                    Icon(Icons.Default.AudioFile, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("Choose recording")
                }
            } else {
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
