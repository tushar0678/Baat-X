package com.baatx.features.reports

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.AiGeneratedLabel
import com.baatx.core.ui.ErrorState
import com.baatx.core.ui.LoadingState
import com.baatx.core.ui.StatCard

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportsScreen(viewModel: ReportsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Reports") }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = state.tabIndex) {
                listOf("Daily", "Weekly", "Monthly").forEachIndexed { index, label ->
                    Tab(
                        selected = state.tabIndex == index,
                        onClick = { viewModel.selectTab(index) },
                        text = { Text(label) },
                    )
                }
            }

            when {
                state.isLoading -> LoadingState()
                state.error != null -> ErrorState(state.error!!, onRetry = viewModel::refresh)
                else -> LazyColumn(
                    contentPadding = PaddingValues(16.dp, 16.dp, 16.dp, 96.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    item { Text(state.title, style = MaterialTheme.typography.titleLarge) }
                    item {
                        Text(
                            state.periodLabel,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }

                    // Every number below is counted from the database, never estimated.
                    items(state.metrics.chunked(2)) { pair ->
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                            pair.forEach { (label, value) ->
                                StatCard("$value", label, Modifier.weight(1f))
                            }
                            if (pair.size == 1) Spacer(Modifier.weight(1f))
                        }
                    }

                    if (state.insights.isNotEmpty()) {
                        item {
                            Spacer(Modifier.height(8.dp))
                            Text("AI INSIGHTS", style = MaterialTheme.typography.labelLarge)
                            AiGeneratedLabel()
                        }
                        items(state.insights) { insight ->
                            Card(Modifier.fillMaxWidth()) {
                                Text(
                                    insight,
                                    style = MaterialTheme.typography.bodyMedium,
                                    modifier = Modifier.padding(16.dp),
                                )
                            }
                        }
                    }

                    if (state.importantFollowUps.isNotEmpty()) {
                        item {
                            Spacer(Modifier.height(8.dp))
                            Text("IMPORTANT FOLLOW-UPS", style = MaterialTheme.typography.labelLarge)
                        }
                        items(state.importantFollowUps) { (name, action) ->
                            ListItem(
                                headlineContent = { Text(name) },
                                supportingContent = { Text(action) },
                            )
                            HorizontalDivider()
                        }
                    }
                }
            }
        }
    }
}

private inline fun <T> androidx.compose.foundation.lazy.LazyListScope.items(
    list: List<T>,
    crossinline block: @Composable (T) -> Unit,
) = items(list.size) { index -> block(list[index]) }
