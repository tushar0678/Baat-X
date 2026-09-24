package com.baatx.features.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.domain.repository.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

data class AuthUiState(
    val isLoading: Boolean = false,
    val isSignupMode: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {

    val isSignedIn: StateFlow<Boolean> = repository.isSignedIn
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    private val _state = MutableStateFlow(AuthUiState())
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    fun toggleMode() {
        _state.value = _state.value.copy(isSignupMode = !_state.value.isSignupMode, error = null)
    }

    fun login(email: String, password: String) = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)
        when (val result = repository.login(email, password)) {
            is ApiResult.Success -> _state.value = _state.value.copy(isLoading = false)
            is ApiResult.Failure ->
                _state.value = _state.value.copy(isLoading = false, error = result.error.message)
        }
    }

    fun signup(
        fullName: String,
        email: String,
        password: String,
        businessName: String,
        vertical: String,
    ) = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)
        val result = repository.signup(fullName, email, password, businessName, vertical)
        _state.value = when (result) {
            is ApiResult.Success -> _state.value.copy(isLoading = false)
            is ApiResult.Failure -> _state.value.copy(isLoading = false, error = result.error.message)
        }
    }

    fun signOut() = repository.signOut()

    fun currentUserName(): String? = repository.currentUserName()
}
