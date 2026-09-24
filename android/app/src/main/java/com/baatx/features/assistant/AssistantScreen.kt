package com.baatx.features.assistant

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

private val SUGGESTIONS = listOf(
    "Today's follow-ups batao",
    "Rajesh se last baar kya baat hui thi?",
    "₹50 lakh se upar budget wale customers dikhao",
    "Price concern wale customers dikhao",
    "This week kitne leads convert hue?",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AssistantScreen(
    onBack: () -> Unit,
    viewModel: AssistantViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var input by rememberSaveable { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Ask BaatX") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            LazyColumn(
                modifier = Modifier.weight(1f),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                if (state.messages.isEmpty()) {
                    item {
                        Text(
                            "Ask about your customers, follow-ups and conversions.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    items(SUGGESTIONS) { suggestion ->
                        SuggestionChip(
                            onClick = { viewModel.ask(suggestion) },
                            label = { Text(suggestion) },
                        )
                    }
                }

                items(state.messages) { message -> MessageBubble(message) }

                if (state.pendingConfirmation != null) {
                    item {
                        // Destructive actions always ask first (§23).
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = viewModel::confirmPending) { Text("Yes, do it") }
                            OutlinedButton(onClick = viewModel::cancelPending) { Text("Cancel") }
                        }
                    }
                }
            }

            if (state.isLoading) LinearProgressIndicator(Modifier.fillMaxWidth())

            Row(
                Modifier.fillMaxWidth().padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OutlinedTextField(
                    value = input,
                    onValueChange = { input = it },
                    placeholder = { Text("Ask anything about your CRM") },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(24.dp),
                    maxLines = 3,
                )
                Spacer(Modifier.width(8.dp))
                FilledIconButton(
                    onClick = {
                        viewModel.ask(input)
                        input = ""
                    },
                    enabled = input.isNotBlank() && !state.isLoading,
                ) {
                    Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Send")
                }
            }
        }
    }
}

@Composable
private fun MessageBubble(message: AssistantMessage) {
    val isUser = message.fromUser
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            color = if (isUser) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.surfaceVariant
            },
            shape = RoundedCornerShape(16.dp),
            modifier = Modifier.widthIn(max = 300.dp),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(message.text, style = MaterialTheme.typography.bodyMedium)
                message.rows.forEach { row ->
                    Spacer(Modifier.height(6.dp))
                    Text(row, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}