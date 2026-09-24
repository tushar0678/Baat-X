package com.baatx.features.customers

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.model.Customer
import com.baatx.domain.model.LeadStatus
import com.baatx.domain.repository.CustomerRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class CustomersUiState(
    val isLoading: Boolean = true,
    val customers: List<Customer> = emptyList(),
    val search: String = "",
    val statusFilter: LeadStatus? = null,
    val error: String? = null,
)

@HiltViewModel
class CustomersViewModel @Inject constructor(
    private val repository: CustomerRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(CustomersUiState())
    val state: StateFlow<CustomersUiState> = _state.asStateFlow()

    private var searchJob: Job? = null

    init {
        refresh()
    }

    fun onSearchChange(value: String) {
        _state.value = _state.value.copy(search = value)
        // Debounced so a salesperson typing on 3G doesn't fire a request per keystroke.
        searchJob?.cancel()
        searchJob = viewModelScope.launch {
            delay(350)
            refresh()
        }
    }

    fun onStatusChange(status: LeadStatus?) {
        _state.value = _state.value.copy(statusFilter = status)
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        val current = _state.value
        _state.value = current.copy(isLoading = true, error = null)
        _state.value = when (
            val result = repository.list(current.search, current.statusFilter, page = 1)
        ) {
            is ApiResult.Success -> current.copy(isLoading = false, customers = result.data)
            is ApiResult.Failure -> current.copy(isLoading = false, error = result.error.message)
        }
    }
}
