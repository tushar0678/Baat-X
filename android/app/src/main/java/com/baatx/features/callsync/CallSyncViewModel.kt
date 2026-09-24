package com.baatx.features.callsync

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.calls.CallSyncNotifier
import com.baatx.core.network.ApiResult
import com.baatx.data.local.PendingCallDao
import com.baatx.data.local.PendingCallEntity
import com.baatx.domain.repository.ConversationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class CallSyncUiState(
    val isLoading: Boolean = true,
    val call: PendingCallEntity? = null,
    val phoneNumber: String = "",
    val contactName: String = "",
    val recordingPath: String? = null,
    val recordingMimeType: String? = null,
    val recordingName: String? = null,
    val consentGiven: Boolean = false,
    val isSubmitting: Boolean = false,
    val queuedOffline: Boolean = false,
    val startedJobId: String? = null,
    val finished: Boolean = false,
    val error: String? = null,
) {
    /**
     * Nothing is uploaded until there is a recording, a number to attach it to,
     * and an explicit consent tick.
     */
    val canSync: Boolean
        get() = !isSubmitting &&
            recordingPath != null &&
            phoneNumber.filter(Char::isDigit).length >= 8 &&
            consentGiven
}

@HiltViewModel
class CallSyncViewModel @Inject constructor(
    private val pendingCallDao: PendingCallDao,
    private val conversations: ConversationRepository,
    private val notifier: CallSyncNotifier,
) : ViewModel() {

    private val _state = MutableStateFlow(CallSyncUiState())
    val state: StateFlow<CallSyncUiState> = _state.asStateFlow()

    fun load(callId: String) = viewModelScope.launch {
        notifier.dismiss(callId)
        val call = pendingCallDao.byId(callId)
        _state.value = CallSyncUiState(
            isLoading = false,
            call = call,
            phoneNumber = call?.phoneNumber.orEmpty(),
            contactName = call?.contactName.orEmpty(),
            // Call log access may be denied, in which case we simply ask.
            error = if (call != null && call.phoneNumber.isNullOrBlank()) {
                "We couldn't read the number of that call. Please enter it below."
            } else {
                null
            },
        )
    }

    fun onPhoneChange(value: String) {
        _state.value = _state.value.copy(phoneNumber = value, error = null)
    }

    fun onNameChange(value: String) {
        _state.value = _state.value.copy(contactName = value)
    }

    fun onConsentChange(value: Boolean) {
        _state.value = _state.value.copy(consentGiven = value)
    }

    fun onRecordingPicked(path: String, mimeType: String, displayName: String?) {
        _state.value = _state.value.copy(
            recordingPath = path,
            recordingMimeType = mimeType,
            recordingName = displayName,
            error = null,
        )
    }

    fun clearRecording() {
        _state.value = _state.value.copy(
            recordingPath = null,
            recordingMimeType = null,
            recordingName = null,
        )
    }

    fun onPickFailed() {
        _state.value = _state.value.copy(
            error = "This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG.",
        )
    }

    /**
     * Submits the recording with the call's contact attached. The server
     * matches on the phone number, so a repeat call from the same person
     * updates the existing customer instead of creating a new one.
     */
    fun sync() = viewModelScope.launch {
        val current = _state.value
        val path = current.recordingPath ?: return@launch
        _state.value = current.copy(isSubmitting = true, error = null)

        val result = conversations.importAudio(
            localPath = path,
            mimeType = current.recordingMimeType ?: "audio/mpeg",
            source = "import_call_recording",
            phoneHint = current.phoneNumber.trim(),
            nameHint = current.contactName.trim().takeIf { it.isNotBlank() },
        )

        _state.value = when (result) {
            is ApiResult.Success -> {
                current.call?.let {
                    pendingCallDao.setStatus(
                        it.id,
                        PendingCallEntity.STATUS_SYNCED,
                        result.data?.id,
                    )
                }
                _state.value.copy(
                    isSubmitting = false,
                    startedJobId = result.data?.id,
                    queuedOffline = result.data == null,
                )
            }
            is ApiResult.Failure ->
                _state.value.copy(isSubmitting = false, error = result.error.message)
        }
    }

    fun dismissCall() = viewModelScope.launch {
        _state.value.call?.let {
            pendingCallDao.setStatus(it.id, PendingCallEntity.STATUS_DISMISSED)
            notifier.dismiss(it.id)
        }
        _state.value = _state.value.copy(finished = true)
    }

    fun consumeNavigation() {
        _state.value = _state.value.copy(startedJobId = null)
    }
}
