package com.baatx.features.tellai

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Autorenew
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.ConfidenceChip
import com.baatx.core.ui.ErrorState
import com.baatx.domain.model.DetectedFollowUp
import com.baatx.domain.model.ReviewItem
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val DUE_FORMAT = DateTimeFormatter.ofPattern("EEEE, d MMM 'at' h:mm a")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiReviewScreen(
    jobId: String,
    onDone: () -> Unit,
    onBack: () -> Unit,
    viewModel: AiReviewViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(jobId) { viewModel.observeJob(jobId) }
    LaunchedEffect(state.savedCustomerId) { if (state.savedCustomerId != null) onDone() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Here's what I understood") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when {
                state.error != null && state.review == null ->
                    ErrorState(state.error!!, onRetry = { viewModel.reanalyze(jobId) })

                state.review == null -> ProcessingProgress(
                    stage = state.job?.stageLabel ?: "Uploading audio...",
                    progress = state.job?.progress ?: 0,
                )

                else -> ReviewContent(
                    items = state.review!!.items,
                    summary = state.review!!.summary,
                    followUp = state.review!!.followUp,
                    matchedExisting = state.review!!.matchedExistingCustomer,
                    confirmFollowUp = state.confirmFollowUp,
                    isSaving = state.isSaving,
                    error = state.error,
                    onConfirmFollowUpChange = viewModel::setConfirmFollowUp,
                    onSave = viewModel::save,
                    onReanalyze = { viewModel.reanalyze(jobId) },
                    onDiscard = { viewModel.discard(onDone) },
                )
            }
        }
    }
}

@Composable
private fun ProcessingProgress(stage: String, progress: Int) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        CircularProgressIndicator()
        Spacer(Modifier.height(24.dp))
        Text(stage, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        Spacer(Modifier.height(12.dp))
        LinearProgressIndicator(
            progress = { progress / 100f },
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(8.dp))
        Text("Processing $progress%", style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun ReviewContent(
    items: List<ReviewItem>,
    summary: String?,
    followUp: DetectedFollowUp,
    matchedExisting: Boolean,
    confirmFollowUp: Boolean,
    isSaving: Boolean,
    error: String?,
    onConfirmFollowUpChange: (Boolean) -> Unit,
    onSave: () -> Unit,
    onReanalyze: () -> Unit,
    onDiscard: () -> Unit,
) {
    LazyColumn(
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (matchedExisting) {
            item {
                AssistChip(
                    onClick = {},
                    label = { Text("Matched an existing customer") },
                )
            }
        }

        items(items) { item ->
            Card(shape = RoundedCornerShape(14.dp), modifier = Modifier.fillMaxWidth()) {
                Column(Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            item.label,
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.weight(1f),
                        )
                        ConfidenceChip(item.band)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(item.value, style = MaterialTheme.typography.titleMedium)
                    if (item.needsConfirmation) {
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "Please confirm this one.",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.error,
                        )
                    }
                }
            }
        }

        if (!summary.isNullOrBlank()) {
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Text("Summary", style = MaterialTheme.typography.labelLarge)
                        Spacer(Modifier.height(4.dp))
                        Text(summary, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }

        if (followUp.required) {
            item {
                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                    ),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.NotificationsActive, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text(
                                "AI detected a follow-up",
                                style = MaterialTheme.typography.titleMedium,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Text(
                            followUp.action ?: followUp.type.label,
                            style = MaterialTheme.typography.bodyLarge,
                        )
                        val due = followUp.resolvedDueAt
                        Text(
                            when {
                                due != null ->
                                    DUE_FORMAT.format(due.atZone(ZoneId.systemDefault()))
                                followUp.rawDate != null ->
                                    "Heard: \"${followUp.rawDate}\" — we couldn't pin a date."
                                else -> "No date detected."
                            },
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        if (followUp.needsConfirmation) {
                            Spacer(Modifier.height(6.dp))
                            // BaatX asks rather than inventing a date (§7, §13).
                            Text(
                                "Please confirm the exact day before saving.",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        }
                        Spacer(Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Switch(checked = confirmFollowUp, onCheckedChange = onConfirmFollowUpChange)
                            Spacer(Modifier.width(8.dp))
                            Text("Create this reminder")
                        }
                    }
                }
            }
        }

        if (error != null) {
            item {
                Text(
                    error,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }

        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onSave,
                    enabled = !isSaving,
                    modifier = Modifier.fillMaxWidth().height(50.dp),
                ) {
                    if (isSaving) {
                        CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp)
                    } else {
                        Icon(Icons.Default.Check, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Save to CRM")
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onReanalyze, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Default.Autorenew, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Re-analyze")
                    }
                    OutlinedButton(onClick = onDiscard, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Default.Delete, contentDescription = null)
                        Spacer(Modifier.width(6.dp))
                        Text("Discard")
                    }
                }
            }
        }
    }
}
