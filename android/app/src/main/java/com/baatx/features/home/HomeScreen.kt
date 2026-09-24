package com.baatx.features.home

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AudioFile
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.*
import com.baatx.domain.model.AIActivity

@Composable
fun HomeScreen(
    onTellAi: () -> Unit,
    onOpenFollowUps: () -> Unit,
    onOpenCustomer: (String) -> Unit,
    onJobStarted: (String) -> Unit,
    viewModel: HomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val pending by viewModel.pendingUploads.collectAsStateWithLifecycle()

    Column(Modifier.fillMaxSize()) {
        OfflineBanner(pending)

        when {
            state.isLoading && state.dashboard == null -> LoadingState()
            state.error != null && state.dashboard == null ->
                ErrorState(state.error!!, onRetry = viewModel::refresh)
            else -> {
                val dashboard = state.dashboard ?: return@Column
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 96.dp),
                    verticalArrangement = Arrangement.spacedBy(16.dp),
                ) {
                    item {
                        Text(dashboard.greeting, style = MaterialTheme.typography.headlineSmall)
                        Spacer(Modifier.height(4.dp))
                        Text(
                            dashboard.prompt,
                            style = MaterialTheme.typography.bodyLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    item { PrimaryActions(onTellAi = onTellAi) }

                    item {
                        SectionHeader("TODAY", onClick = onOpenFollowUps)
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            StatCard(
                                "${dashboard.followUpsToday}",
                                "Follow-ups",
                                Modifier.weight(1f),
                            )
                            StatCard("${dashboard.newLeads}", "New Leads", Modifier.weight(1f))
                        }
                        Spacer(Modifier.height(12.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            StatCard(
                                "${dashboard.hotLeads}",
                                "Hot Leads",
                                Modifier.weight(1f),
                                accent = MaterialTheme.colorScheme.tertiary,
                            )
                            StatCard(
                                "${dashboard.overdue}",
                                "Overdue",
                                Modifier.weight(1f),
                                accent = MaterialTheme.colorScheme.error,
                            )
                        }
                    }

                    item {
                        SectionHeader("CONVERSIONS")
                        Spacer(Modifier.height(8.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            StatCard(
                                "${dashboard.newCustomers}",
                                "New Customers",
                                Modifier.weight(1f),
                            )
                            StatCard(
                                "${dashboard.convertedToday}",
                                "Converted Today",
                                Modifier.weight(1f),
                                accent = MaterialTheme.colorScheme.secondary,
                            )
                        }
                    }

                    if (dashboard.aiActivity.isNotEmpty()) {
                        item { SectionHeader("AI ACTIVITY") }
                        items(dashboard.aiActivity) { activity ->
                            AiActivityRow(activity, onOpenCustomer)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun PrimaryActions(onTellAi: () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        // Tell AI is the single most important action on the whole screen.
        Card(
            onClick = onTellAi,
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer,
            ),
            shape = RoundedCornerShape(20.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Row(
                Modifier.padding(20.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(Icons.Default.Mic, contentDescription = null, Modifier.size(32.dp))
                Spacer(Modifier.width(16.dp))
                Column {
                    Text("Tell AI", style = MaterialTheme.typography.titleLarge)
                    Text(
                        "Just say what happened with your customer",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }
        }

        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            OutlinedCard(onClick = onTellAi, modifier = Modifier.weight(1f)) {
                Column(Modifier.padding(16.dp)) {
                    Icon(Icons.Default.Phone, contentDescription = null)
                    Spacer(Modifier.height(8.dp))
                    Text("Import Call Recording", style = MaterialTheme.typography.bodyMedium)
                }
            }
            OutlinedCard(onClick = onTellAi, modifier = Modifier.weight(1f)) {
                Column(Modifier.padding(16.dp)) {
                    Icon(Icons.Default.AudioFile, contentDescription = null)
                    Spacer(Modifier.height(8.dp))
                    Text("Import Audio", style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(title: String, onClick: (() -> Unit)? = null) {
    Text(
        title,
        style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier,
    )
}

@Composable
private fun AiActivityRow(activity: AIActivity, onOpenCustomer: (String) -> Unit) {
    ListItem(
        headlineContent = { Text(activity.customerName ?: "Customer") },
        supportingContent = { Text(activity.action) },
        modifier = Modifier.clickable {
            activity.customerId?.let(onOpenCustomer)
        },
    )
    HorizontalDivider()
}
