package com.baatx.features.followups

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.EmptyState
import com.baatx.core.ui.ErrorState
import com.baatx.core.ui.LoadingState
import com.baatx.domain.model.FollowUp
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val TIME_FORMAT = DateTimeFormatter.ofPattern("h:mm a")
private val DATE_FORMAT = DateTimeFormatter.ofPattern("d MMM, h:mm a")

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FollowUpsScreen(
    onOpenCustomer: (String) -> Unit,
    viewModel: FollowUpsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Follow-ups") }) }) { padding ->
        Box(Modifier.fillMaxSize().padding(padding)) {
            when {
                state.isLoading && state.board == null -> LoadingState()
                state.error != null && state.board == null ->
                    ErrorState(state.error!!, onRetry = viewModel::refresh)
                else -> {
                    val board = state.board
                    if (board == null ||
                        listOf(board.overdue, board.today, board.tomorrow, board.upcoming)
                            .all { it.isEmpty() }
                    ) {
                        EmptyState(
                            "No follow-ups yet",
                            "Tell BaatX about a conversation and reminders appear here automatically.",
                        )
                        return@Box
                    }

                    LazyColumn(
                        contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 96.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        section("OVERDUE", board.overdue, onOpenCustomer, viewModel)
                        section("TODAY", board.today, onOpenCustomer, viewModel)
                        section("TOMORROW", board.tomorrow, onOpenCustomer, viewModel)
                        section("UPCOMING", board.upcoming, onOpenCustomer, viewModel)
                        section("COMPLETED", board.completed, onOpenCustomer, viewModel, done = true)
                    }
                }
            }
        }
    }
}

private fun androidx.compose.foundation.lazy.LazyListScope.section(
    title: String,
    items: List<FollowUp>,
    onOpenCustomer: (String) -> Unit,
    viewModel: FollowUpsViewModel,
    done: Boolean = false,
) {
    if (items.isEmpty()) return
    item(key = "header-$title") {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            Text(title, style = MaterialTheme.typography.labelLarge)
            Spacer(Modifier.width(8.dp))
            Badge { Text("${items.size}") }
        }
    }
    items(items, key = { it.id }) { followUp ->
        FollowUpRow(
            followUp = followUp,
            showActions = !done,
            onOpenCustomer = onOpenCustomer,
            onDone = { viewModel.markDone(followUp.id) },
            onSnooze = { viewModel.snoozeToTomorrow(followUp.id) },
        )
    }
}

@Composable
private fun FollowUpRow(
    followUp: FollowUp,
    showActions: Boolean,
    onOpenCustomer: (String) -> Unit,
    onDone: () -> Unit,
    onSnooze: () -> Unit,
) {
    val zoned = followUp.dueAt.atZone(ZoneId.systemDefault())
    Card(
        onClick = { onOpenCustomer(followUp.customerId) },
        colors = CardDefaults.cardColors(
            containerColor = if (followUp.isOverdue) {
                MaterialTheme.colorScheme.errorContainer
            } else {
                MaterialTheme.colorScheme.surface
            },
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(
                followUp.customerName ?: "Customer",
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(2.dp))
            Text(followUp.title, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(2.dp))
            Text(
                if (followUp.isOverdue) {
                    "Overdue — was due ${DATE_FORMAT.format(zoned)}"
                } else {
                    TIME_FORMAT.format(zoned)
                },
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (followUp.customerRequestedCallback) {
                Spacer(Modifier.height(4.dp))
                AssistChip(onClick = {}, label = { Text("Customer asked for a callback") })
            }

            if (showActions) {
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilledTonalButton(onClick = onDone) {
                        Icon(Icons.Default.Check, contentDescription = null, Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Done")
                    }
                    OutlinedButton(onClick = onSnooze) {
                        Icon(Icons.Default.Schedule, contentDescription = null, Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Tomorrow")
                    }
                    if (followUp.phoneMasked != null) {
                        OutlinedButton(onClick = { onOpenCustomer(followUp.customerId) }) {
                            Icon(Icons.Default.Phone, contentDescription = null, Modifier.size(18.dp))
                        }
                    }
                }
            }
        }
    }
}
