package com.baatx.features.tellai

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.model.ExtractionReview
import com.baatx.domain.model.ProcessingJob
import com.baatx.domain.repository.ConversationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class ReviewUiState(
    val job: ProcessingJob? = null,
    val review: ExtractionReview? = null,
    val edits: Map<String, String> = emptyMap(),
    val confirmFollowUp: Boolean = true,
    val isSaving: Boolean = false,
    val savedCustomerId: String? = null,
    val error: String? = null,
)

@HiltViewModel
class AiReviewViewModel @Inject constructor(
    private val conversations: ConversationRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ReviewUiState())
    val state: StateFlow<ReviewUiState> = _state.asStateFlow()

    /**
     * Polls job progress until the extraction is ready. The backend drives the
     * stage labels ("Understanding conversation…", "Processing 62%"), so the UI
     * never invents progress it doesn't have.
     */
    fun observeJob(jobId: String) = viewModelScope.launch {
        repeat(MAX_POLLS) {
            when (val result = conversations.jobStatus(jobId)) {
                is ApiResult.Success -> {
                    val job = result.data
                    _state.value = _state.value.copy(job = job)
                    when {
                        job.isReadyForReview -> {
                            loadReview(jobId)
                            return@launch
                        }
                        job.isFailed -> {
                            _state.value = _state.value.copy(
                                error = job.errorMessage
                                    ?: "Something went wrong while processing your recording. Please try again.",
                            )
                            return@launch
                        }
                    }
                }

                is ApiResult.Failure -> {
                    if (!result.error.isRetryable) {
                        _state.value = _state.value.copy(error = result.error.message)
                        return@launch
                    }
                    // 429s here are transient (rate limiting), not a job
                    // failure - keep polling instead of surfacing an error.
                }
            }
            delay(POLL_INTERVAL_MS)
        }
        _state.value = _state.value.copy(
            error = "This is taking longer than usual. We'll notify you when it's ready.",
        )
    }

    /**
     * The job is already `awaiting_review` by the time this is called, so a
     * transient failure here (e.g. a 429 from polling too aggressively while
     * the job just finished) must not be treated as terminal - the extraction
     * exists and is waiting, it just couldn't be fetched on this attempt.
     * Without this retry, the UI got stuck showing the job's last known
     * progress (often still 5%, from before processing started) forever,
     * with no further polling and no way to recover short of restarting the
     * whole capture.
     */
    private suspend fun loadReview(jobId: String, attempt: Int = 0) {
        when (val result = conversations.review(jobId)) {
            is ApiResult.Success ->
                _state.value = _state.value.copy(review = result.data, error = null)

            is ApiResult.Failure -> {
                if (result.error.isRetryable && attempt < MAX_REVIEW_RETRIES) {
                    delay(REVIEW_RETRY_DELAY_MS)
                    loadReview(jobId, attempt + 1)
                } else {
                    _state.value = _state.value.copy(error = result.error.message)
                }
            }
        }
    }

    fun edit(key: String, value: String) {
        _state.value = _state.value.copy(edits = _state.value.edits + (key to value))
    }

    fun setConfirmFollowUp(confirm: Boolean) {
        _state.value = _state.value.copy(confirmFollowUp = confirm)
    }

    fun save() = viewModelScope.launch {
        val review = _state.value.review ?: return@launch
        _state.value = _state.value.copy(isSaving = true, error = null)
        val result = conversations.apply(
            extractionId = review.extractionId,
            edits = _state.value.edits,
            confirmFollowUp = _state.value.confirmFollowUp,
            customerId = review.customerId,
        )
        _state.value = when (result) {
            is ApiResult.Success ->
                _state.value.copy(isSaving = false, savedCustomerId = result.data.customerId)
            is ApiResult.Failure ->
                _state.value.copy(isSaving = false, error = result.error.message)
        }
    }

    fun reanalyze(jobId: String) = viewModelScope.launch {
        _state.value = _state.value.copy(review = null, error = null)
        when (val result = conversations.reanalyze(jobId)) {
            is ApiResult.Success -> observeJob(jobId)
            is ApiResult.Failure -> _state.value = _state.value.copy(error = result.error.message)
        }
    }

    fun discard(onDone: () -> Unit) = viewModelScope.launch {
        val review = _state.value.review ?: return@launch run { onDone() }
        conversations.discard(review.extractionId)
        onDone()
    }

    /** Manual "Try again" action for the stuck/error state, without restarting the whole job. */
    fun retryLoadReview(jobId: String) = viewModelScope.launch {
        _state.value = _state.value.copy(error = null)
        loadReview(jobId)
    }

    private companion object {
        const val POLL_INTERVAL_MS = 3_000L   // was 2s; reduces 429s from aggressive polling
        const val MAX_POLLS = 150             // supports long recordings (~7.5 minutes of polling)
        const val REVIEW_RETRY_DELAY_MS = 2_000L
        const val MAX_REVIEW_RETRIES = 5
    }
}
