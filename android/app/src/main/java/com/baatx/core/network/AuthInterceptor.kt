package com.baatx.core.network

import com.baatx.core.security.TokenStore
import com.baatx.data.remote.AuthApi
import com.baatx.data.remote.dto.RefreshRequest
import dagger.Lazy
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.runBlocking
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

/** Attaches the bearer token and the active tenant to every request. */
@Singleton
class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        if (original.header("No-Auth") != null) {
            return chain.proceed(original.newBuilder().removeHeader("No-Auth").build())
        }

        val builder = original.newBuilder()
        tokenStore.accessToken?.let { builder.header("Authorization", "Bearer $it") }
        tokenStore.businessId?.let { builder.header("X-Business-Id", it) }
        return chain.proceed(builder.build())
    }
}

/**
 * Refreshes the access token exactly once per 401 and replays the request.
 * If the refresh itself fails, the session is cleared and the user is asked to
 * sign in again.
 */
@Singleton
class TokenAuthenticator @Inject constructor(
    private val tokenStore: TokenStore,
    private val authApi: Lazy<AuthApi>,
) : Authenticator {

    override fun authenticate(route: Route?, response: Response): Request? {
        if (response.request.header("Authorization") == null) return null
        if (responseCount(response) >= 2) return null

        val refresh = tokenStore.refreshToken ?: return null

        val refreshed = runCatching {
            runBlocking { authApi.get().refresh(RefreshRequest(refresh)) }
        }.getOrElse {
            tokenStore.clear()
            return null
        }

        tokenStore.updateAccess(refreshed.accessToken, refreshed.refreshToken)
        return response.request.newBuilder()
            .header("Authorization", "Bearer ${refreshed.accessToken}")
            .build()
    }

    private fun responseCount(response: Response): Int {
        var count = 1
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}
