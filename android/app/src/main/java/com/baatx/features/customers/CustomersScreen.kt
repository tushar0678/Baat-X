package com.baatx.features.customers

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.ui.EmptyState
import com.baatx.core.ui.ErrorState
import com.baatx.core.ui.LoadingState
import com.baatx.domain.model.Customer
import com.baatx.domain.model.LeadStatus

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomersScreen(
    onOpenCustomer: (String) -> Unit,
    viewModel: CustomersViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(topBar = { TopAppBar(title = { Text("Customers") }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            OutlinedTextField(
                value = state.search,
                onValueChange = viewModel::onSearchChange,
                placeholder = { Text("Search name, phone or requirement") },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
            )

            ScrollableTabRow(
                selectedTabIndex = FILTERS.indexOfFirst { it.second == state.statusFilter }
                    .coerceAtLeast(0),
                edgePadding = 16.dp,
            ) {
                FILTERS.forEach { (label, status) ->
                    Tab(
                        selected = state.statusFilter == status,
                        onClick = { viewModel.onStatusChange(status) },
                        text = { Text(label) },
                    )
                }
            }

            when {
                state.isLoading && state.customers.isEmpty() -> LoadingState()
                state.error != null && state.customers.isEmpty() ->
                    ErrorState(state.error!!, onRetry = viewModel::refresh)
                state.customers.isEmpty() ->
                    EmptyState(
                        "No customers yet",
                        "Tap Tell AI after your next conversation and BaatX will add them for you.",
                    )
                else -> LazyColumn(
                    contentPadding = PaddingValues(16.dp, 8.dp, 16.dp, 96.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.customers, key = { it.id }) { customer ->
                        CustomerRow(customer) { onOpenCustomer(customer.id) }
                    }
                }
            }
        }
    }
}

private val FILTERS = listOf(
    "All" to null,
    "Hot" to LeadStatus.HOT,
    "Interested" to LeadStatus.INTERESTED,
    "Follow-up" to LeadStatus.FOLLOW_UP,
    "New" to LeadStatus.NEW,
    "Converted" to LeadStatus.CONVERTED,
)

@Composable
private fun CustomerRow(customer: Customer, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    customer.name ?: "Unnamed customer",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.weight(1f),
                )
                AssistChip(onClick = {}, label = { Text(customer.leadStatus.label) })
            }
            customer.phoneMasked?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            val details = listOfNotNull(
                customer.requirement,
                customer.budgetLabel,
                customer.location,
            )
            if (details.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(details.joinToString(" • "), style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}
