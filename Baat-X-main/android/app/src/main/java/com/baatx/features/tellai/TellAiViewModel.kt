package com.baatx.features.tellai

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.repository.ConversationRepository
import com.baatx.features.audio.AudioRecorder
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class TellAiUiState(
    val isRecording: Boolean = false,
    val isSubmitting: Boolean = false,
    val text: String = "",
    val queuedOffline: Boolean = false,
    val startedJobId: String? = null,
    val error: String? = null,
)

@HiltViewModel
class TellAiViewModel @Inject constructor(
    private val conversations: ConversationRepository,
    private val recorder: AudioRecorder,
) : ViewModel() {

    private val _state = MutableStateFlow(TellAiUiState())
    val state: StateFlow<TellAiUiState> = _state.asStateFlow()

    fun onTextChange(value: String) {
        _state.value = _state.value.copy(text = value, error = null)
    }

    fun startRecording() {
        runCatching { recorder.start() }
            .onSuccess { _state.value = _state.value.copy(isRecording = true, error = null) }
            .onFailure {
                _state.value = _state.value.copy(
                    isRecording = false,
                    error = "We couldn't start recording. Please check microphone permission.",
                )
            }
    }

    fun cancelRecording() {
        recorder.cancel()
        _state.value = _state.value.copy(isRecording = false)
    }

    /** Stops the recording and submits it as an audio capture. */
    fun stopAndSubmitRecording() = viewModelScope.launch {
        val file = recorder.stop()
        _state.value = _state.value.copy(isRecording = false)
        if (file == null) {
            _state.value = _state.value.copy(
                error = "That recording was too short. Please try again.",
            )
            return@launch
        }
        submit {
            conversations.importAudio(
                localPath = file.absolutePath,
                mimeType = "audio/mp4",
                source = "tell_ai",
            )
        }
    }

    fun submitText() = viewModelScope.launch {
        val text = _state.value.text.trim()
        if (text.length < 3) {
            _state.value = _state.value.copy(error = "Please say a little more about the conversation.")
            return@launch
        }
        submit { conversations.tellAi(text) }
    }

    fun submitImportedAudio(path: String, mimeType: String, isCallRecording: Boolean) =
        viewModelScope.launch {
            submit {
                conversations.importAudio(
                    localPath = path,
                    mimeType = mimeType,
                    source = if (isCallRecording) "import_call_recording" else "import_audio",
                )
            }
        }

    private suspend fun submit(block: suspend () -> ApiResult<com.baatx.domain.model.ProcessingJob?>) {
        _state.value = _state.value.copy(isSubmitting = true, error = null)
        _state.value = when (val result = block()) {
            is ApiResult.Success ->
                // A null job means we're offline and it was queued locally.
                _state.value.copy(
                    isSubmitting = false,
                    startedJobId = result.data?.id,
                    queuedOffline = result.data == null,
                )

            is ApiResult.Failure ->
                _state.value.copy(isSubmitting = false, error = result.error.message)
        }
    }

    fun consumeNavigation() {
        _state.value = _state.value.copy(startedJobId = null)
    }

    override fun onCleared() {
        recorder.cancel()
        super.onCleared()
    }
}
