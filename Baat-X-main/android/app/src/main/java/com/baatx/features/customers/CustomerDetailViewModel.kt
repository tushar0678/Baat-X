package com.baatx.features.customers

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.data.remote.dto.TimelineEntryDto
import com.baatx.domain.model.Customer
import com.baatx.domain.repository.CustomerRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class CustomerDetailUiState(
    val isLoading: Boolean = true,
    val customer: Customer? = null,
    val timeline: List<TimelineEntryDto> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class CustomerDetailViewModel @Inject constructor(
    private val repository: CustomerRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(CustomerDetailUiState())
    val state: StateFlow<CustomerDetailUiState> = _state.asStateFlow()

    fun load(customerId: String) = viewModelScope.launch {
        _state.value = CustomerDetailUiState(isLoading = true)

        when (val customer = repository.get(customerId)) {
            is ApiResult.Success -> {
                val timeline = repository.timeline(customerId).getOrNull()?.entries.orEmpty()
                _state.value = CustomerDetailUiState(
                    isLoading = false,
                    customer = customer.data,
                    timeline = timeline,
                )
            }

            is ApiResult.Failure ->
                _state.value = CustomerDetailUiState(
                    isLoading = false,
                    error = customer.error.message,
                )
        }
    }
}
