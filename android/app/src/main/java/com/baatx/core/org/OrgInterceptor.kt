package com.baatx.core.org

import javax.inject.Inject
import javax.inject.Singleton
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Stamps every request with the organization the user is currently viewing.
 *
 * Register it *after* `AuthInterceptor` so the token is always present.
 *
 * The server treats this header as untrusted input and re-verifies membership
 * on every request - a tampered value gets a 403, not another tenant's data.
 */
@Singleton
class OrgInterceptor @Inject constructor(
    private val orgContext: OrgContext,
) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()

        // Login, signup and refresh happen before an organization exists.
        if (request.header("No-Auth") != null) {
            return chain.proceed(request)
        }

        val orgId = orgContext.activeOrgId.value
            ?: return chain.proceed(request)

        return chain.proceed(
            request.newBuilder()
                .header("X-Organization-Id", orgId)
                .build(),
        )
    }
}
