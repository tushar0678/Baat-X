package com.baatx.core.network

/**
 * Every repository call returns one of these. UI never sees an exception or an
 * HTTP status code - only a message it can show verbatim.
 */
sealed interface ApiResult<out T> {
    data class Success<T>(val data: T) : ApiResult<T>
    data class Failure(val error: AppError) : ApiResult<Nothing>

    fun getOrNull(): T? = (this as? Success)?.data
}

data class AppError(
    val code: String,
    val message: String,
    val isRetryable: Boolean = false,
    val isOffline: Boolean = false,
    val isAuthError: Boolean = false,
)

inline fun <T, R> ApiResult<T>.map(transform: (T) -> R): ApiResult<R> = when (this) {
    is ApiResult.Success -> ApiResult.Success(transform(data))
    is ApiResult.Failure -> this
}

inline fun <T> ApiResult<T>.onSuccess(action: (T) -> Unit): ApiResult<T> {
    if (this is ApiResult.Success) action(data)
    return this
}

inline fun <T> ApiResult<T>.onFailure(action: (AppError) -> Unit): ApiResult<T> {
    if (this is ApiResult.Failure) action(error)
    return this
}
