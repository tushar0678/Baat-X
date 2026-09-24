package com.baatx.features.home

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.model.DashboardSnapshot
import com.baatx.domain.repository.ConversationRepository
import com.baatx.domain.repository.ReportRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class HomeUiState(
    val isLoading: Boolean = true,
    val dashboard: DashboardSnapshot? = null,
    val error: String? = null,
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val reports: ReportRepository,
    conversations: ConversationRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    /** Drives the "Waiting for internet" banner. */
    val pendingUploads: StateFlow<Int> = conversations.pendingCount()
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), 0)

    init {
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)
        _state.value = when (val result = reports.dashboard()) {
            is ApiResult.Success -> HomeUiState(isLoading = false, dashboard = result.data)
            is ApiResult.Failure -> HomeUiState(isLoading = false, error = result.error.message)
        }
    }
}
