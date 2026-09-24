package com.baatx.features.reports

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.repository.ReportRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ReportsUiState(
    val tabIndex: Int = 0,
    val isLoading: Boolean = true,
    val title: String = "",
    val periodLabel: String = "",
    val metrics: List<Pair<String, Int>> = emptyList(),
    val insights: List<String> = emptyList(),
    val importantFollowUps: List<Pair<String, String>> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val repository: ReportRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ReportsUiState())
    val state: StateFlow<ReportsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun selectTab(index: Int) {
        _state.value = _state.value.copy(tabIndex = index)
        refresh()
    }

    fun refresh() = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)
        when (_state.value.tabIndex) {
            0 -> loadDaily()
            1 -> loadPeriod(weekly = true)
            else -> loadPeriod(weekly = false)
        }
    }

    private suspend fun loadDaily() {
        _state.value = when (val result = repository.daily()) {
            is ApiResult.Success -> {
                val report = result.data
                _state.value.copy(
                    isLoading = false,
                    title = report.title,
                    periodLabel = report.reportDate,
                    metrics = listOf(
                        "New Leads" to report.newLeads,
                        "Customers Contacted" to report.customersContacted,
                        "Interested Leads" to report.interestedLeads,
                        "Hot Leads" to report.hotLeads,
                        "Converted" to report.convertedCustomers,
                        "Follow-ups Completed" to report.followUps.completed,
                        "Follow-ups Pending" to report.followUps.pending,
                        "Overdue Follow-ups" to report.followUps.overdue,
                        "Customer Queries" to report.queries.totalQueries,
                        "Quotations Requested" to report.queries.quotationsRequested,
                        "Price Concerns" to report.queries.priceConcerns,
                        "Callbacks Requested" to report.queries.callbacksRequested,
                    ),
                    insights = report.aiInsights,
                    importantFollowUps = report.importantFollowUps.map {
                        (it.customerName ?: "Customer") to it.action
                    },
                    error = null,
                )
            }

            is ApiResult.Failure -> _state.value.copy(isLoading = false, error = result.error.message)
        }
    }

    private suspend fun loadPeriod(weekly: Boolean) {
        val result = if (weekly) repository.weekly() else repository.monthly()
        _state.value = when (result) {
            is ApiResult.Success -> {
                val report = result.data
                _state.value.copy(
                    isLoading = false,
                    title = report.title,
                    periodLabel = "${report.periodStart} — ${report.periodEnd}",
                    metrics = listOf(
                        "New Leads" to report.leads.newLeads,
                        "Interested" to report.leads.interested,
                        "Hot" to report.leads.hot,
                        "Converted" to report.leads.converted,
                        "Lost" to report.leads.lost,
                        "Conversion Rate %" to report.leads.conversionRate.toInt(),
                        "Follow-ups Created" to report.followUps.created,
                        "Completed" to report.followUps.completed,
                        "Overdue" to report.followUps.overdue,
                        "Customer Queries" to report.queries.totalQueries,
                        "Price Queries" to report.queries.priceConcerns,
                        "Availability Queries" to report.queries.availabilityQueries,
                    ),
                    insights = report.aiInsights,
                    importantFollowUps = report.importantFollowUps.map {
                        (it.customerName ?: "Customer") to it.action
                    },
                    error = null,
                )
            }

            is ApiResult.Failure -> _state.value.copy(isLoading = false, error = result.error.message)
        }
    }
}
