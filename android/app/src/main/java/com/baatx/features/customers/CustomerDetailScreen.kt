package com.baatx.features.customers

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.ErrorState
import com.baatx.core.ui.LoadingState
import com.baatx.data.remote.dto.TimelineEntryDto
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val TIMELINE_FORMAT = DateTimeFormatter.ofPattern("d MMM yyyy, h:mm a")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomerDetailScreen(
    customerId: String,
    onBack: () -> Unit,
    viewModel: CustomerDetailViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(customerId) { viewModel.load(customerId) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.customer?.name ?: "Customer") },
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
                state.isLoading -> LoadingState()
                state.error != null ->
                    ErrorState(state.error!!, onRetry = { viewModel.load(customerId) })
                else -> LazyColumn(
                    contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item {
                        val customer = state.customer ?: return@item
                        Card(Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp)) {
                                customer.phoneMasked?.let {
                                    Text(it, style = MaterialTheme.typography.titleMedium)
                                }
                                Spacer(Modifier.height(8.dp))
                                DetailRow("Requirement", customer.requirement)
                                DetailRow("Budget", customer.budgetLabel)
                                DetailRow("Location", customer.location)
                                DetailRow("Status", customer.leadStatus.label)
                                DetailRow("Intent", customer.purchaseIntent)
                                customer.summary?.let {
                                    Spacer(Modifier.height(8.dp))
                                    Text(it, style = MaterialTheme.typography.bodyMedium)
                                }
                            }
                        }
                    }

                    item {
                        Text("TIMELINE", style = MaterialTheme.typography.labelLarge)
                    }

                    items(state.timeline) { entry -> TimelineRow(entry) }
                }
            }
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Row(Modifier.padding(vertical = 2.dp)) {
        Text(
            "$label: ",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun TimelineRow(entry: TimelineEntryDto) {
    val at = runCatching { Instant.parse(entry.occurredAt) }.getOrNull()
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Text(entry.title, style = MaterialTheme.typography.titleSmall)
            if (at != null) {
                Text(
                    TIMELINE_FORMAT.format(at.atZone(ZoneId.systemDefault())),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            entry.summary?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodyMedium)
            }
            // The timeline stores structured business facts, never audio.
            entry.highlights?.forEach { (key, value) ->
                Text(
                    "${key.replace('_', ' ').replaceFirstChar { it.uppercase() }}: " +
                        value.toString().trim('"'),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}
