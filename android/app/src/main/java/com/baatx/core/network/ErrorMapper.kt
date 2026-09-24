package com.baatx.core.network

import com.baatx.data.remote.dto.ErrorResponse
import java.io.IOException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException
import kotlinx.coroutines.CancellationException
import kotlinx.serialization.json.Json
import retrofit2.HttpException

/**
 * Turns technical failures into the plain-language messages from the product
 * spec (§41). "HTTP 500" never reaches a salesperson's screen.
 */
object ErrorMapper {

    private val json = Json { ignoreUnknownKeys = true }

    fun map(throwable: Throwable): AppError = when (throwable) {
        is UnknownHostException, is SocketTimeoutException -> AppError(
            code = "offline",
            message = "Internet connection was lost. We'll continue when you're back online.",
            isRetryable = true,
            isOffline = true,
        )

        is SSLException -> AppError(
            code = "tls_error",
            message = "We couldn't establish a secure connection. Please try again.",
            isRetryable = true,
        )

        is IOException -> AppError(
            code = "network_error",
            message = "Internet connection was lost. We'll continue when you're back online.",
            isRetryable = true,
            isOffline = true,
        )

        is HttpException -> fromHttp(throwable)

        else -> AppError(
            code = "unknown",
            message = "Something went wrong. Please try again.",
            isRetryable = true,
        )
    }

    private fun fromHttp(exception: HttpException): AppError {
        val body = runCatching {
            exception.response()?.errorBody()?.string()?.let {
                json.decodeFromString<ErrorResponse>(it)
            }
        }.getOrNull()

        val fallback = when (exception.code()) {
            401 -> "Please sign in again."
            403 -> "You don't have permission to do this."
            404 -> "We couldn't find what you were looking for."
            409 -> "This action conflicts with existing data."
            413 -> "This recording is too large to upload. Please try a shorter recording."
            415 -> "This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG."
            429 -> "You're going a bit fast. Please try again in a moment."
            else -> "Something went wrong. Please try again."
        }

        return AppError(
            code = body?.code ?: "http_${exception.code()}",
            // The backend already speaks human; prefer its message.
            message = body?.message ?: fallback,
            isRetryable = exception.code() == 429 || exception.code() >= 500,
            isAuthError = exception.code() == 401,
        )
    }
}

suspend fun <T> safeApiCall(block: suspend () -> T): ApiResult<T> = try {
    ApiResult.Success(block())
} catch (cancellation: CancellationException) {
    throw cancellation
} catch (throwable: Throwable) {
    ApiResult.Failure(ErrorMapper.map(throwable))
}
