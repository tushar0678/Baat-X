package com.baatx.features.followups

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.model.FollowUpBoard
import com.baatx.domain.repository.FollowUpRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.LocalTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class FollowUpsUiState(
    val isLoading: Boolean = true,
    val board: FollowUpBoard? = null,
    val error: String? = null,
)

@HiltViewModel
class FollowUpsViewModel @Inject constructor(
    private val repository: FollowUpRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(FollowUpsUiState())
    val state: StateFlow<FollowUpsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)
        _state.value = when (val result = repository.board(mineOnly = false)) {
            is ApiResult.Success -> FollowUpsUiState(isLoading = false, board = result.data)
            is ApiResult.Failure -> FollowUpsUiState(isLoading = false, error = result.error.message)
        }
    }

    fun markDone(id: String) = viewModelScope.launch {
        when (val result = repository.markDone(id)) {
            is ApiResult.Success -> refresh()
            is ApiResult.Failure -> _state.value = _state.value.copy(error = result.error.message)
        }
    }

    /** Reschedules to 11:00 AM tomorrow - the common "kal dekh lenge" case. */
    fun snoozeToTomorrow(id: String) = viewModelScope.launch {
        val tomorrow = ZonedDateTime.now(ZoneId.systemDefault())
            .plusDays(1)
            .with(LocalTime.of(11, 0))
        val iso = tomorrow.format(DateTimeFormatter.ISO_OFFSET_DATE_TIME)
        when (val result = repository.reschedule(id, iso)) {
            is ApiResult.Success -> refresh()
            is ApiResult.Failure -> _state.value = _state.value.copy(error = result.error.message)
        }
    }
}
