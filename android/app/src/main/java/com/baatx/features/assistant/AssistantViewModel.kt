package com.baatx.features.assistant

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.repository.AssistantRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive

data class AssistantMessage(
    val text: String,
    val fromUser: Boolean,
    val rows: List<String> = emptyList(),
)

data class AssistantUiState(
    val messages: List<AssistantMessage> = emptyList(),
    val isLoading: Boolean = false,
    val pendingConfirmation: PendingConfirmation? = null,
)

data class PendingConfirmation(val query: String, val token: String)

@HiltViewModel
class AssistantViewModel @Inject constructor(
    private val repository: AssistantRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    fun ask(query: String, confirmToken: String? = null) {
        if (query.isBlank()) return
        viewModelScope.launch {
            if (confirmToken == null) {
                _state.value = _state.value.copy(
                    messages = _state.value.messages + AssistantMessage(query, fromUser = true),
                    isLoading = true,
                    pendingConfirmation = null,
                )
            } else {
                _state.value = _state.value.copy(isLoading = true, pendingConfirmation = null)
            }

            when (val result = repository.ask(query, confirmToken)) {
                is ApiResult.Success -> {
                    val response = result.data
                    val rows = response.data.take(10).map { row ->
                        row.entries.joinToString(" • ") { (key, value) ->
                            val rendered = (value as? JsonPrimitive)?.content ?: value.toString()
                            "${key.replace('_', ' ')}: $rendered"
                        }
                    }
                    _state.value = _state.value.copy(
                        messages = _state.value.messages +
                            AssistantMessage(response.answer, fromUser = false, rows = rows),
                        isLoading = false,
                        pendingConfirmation = response.confirmToken?.let {
                            PendingConfirmation(query, it)
                        },
                    )
                }

                is ApiResult.Failure -> _state.value = _state.value.copy(
                    messages = _state.value.messages +
                        AssistantMessage(result.error.message, fromUser = false),
                    isLoading = false,
                )
            }
        }
    }

    fun confirmPending() {
        val pending = _state.value.pendingConfirmation ?: return
        ask(pending.query, pending.token)
    }

    fun cancelPending() {
        _state.value = _state.value.copy(
            pendingConfirmation = null,
            messages = _state.value.messages + AssistantMessage("Okay, cancelled.", fromUser = false),
        )
    }
}
