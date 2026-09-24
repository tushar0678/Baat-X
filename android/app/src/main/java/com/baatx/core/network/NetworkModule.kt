package com.baatx.core.network

import com.baatx.BuildConfig
import com.baatx.data.remote.*
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import java.util.concurrent.TimeUnit
import javax.inject.Singleton
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit

@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun json(): Json = Json {
        ignoreUnknownKeys = true      // the API can add fields without breaking old clients
        explicitNulls = false
        coerceInputValues = true
    }

    @Provides
    @Singleton
    fun okHttp(
        authInterceptor: AuthInterceptor,
        authenticator: TokenAuthenticator,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .authenticator(authenticator)
        .apply {
            if (BuildConfig.DEBUG) {
                // BASIC only: bodies contain customer data and must not be logged.
                addInterceptor(
                    HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC },
                )
            }
        }
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(300, TimeUnit.SECONDS)   // long recordings upload slowly on 3G
        .retryOnConnectionFailure(true)
        .build()

    @Provides
    @Singleton
    fun retrofit(client: OkHttpClient, json: Json): Retrofit = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(client)
        .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
        .build()

    @Provides @Singleton
    fun authApi(retrofit: Retrofit): AuthApi = retrofit.create(AuthApi::class.java)

    @Provides @Singleton
    fun aiApi(retrofit: Retrofit): AiApi = retrofit.create(AiApi::class.java)

    @Provides @Singleton
    fun crmApi(retrofit: Retrofit): CrmApi = retrofit.create(CrmApi::class.java)

    @Provides @Singleton
    fun followUpApi(retrofit: Retrofit): FollowUpApi = retrofit.create(FollowUpApi::class.java)

    @Provides @Singleton
    fun reportApi(retrofit: Retrofit): ReportApi = retrofit.create(ReportApi::class.java)

    @Provides @Singleton
    fun assistantApi(retrofit: Retrofit): AssistantApi = retrofit.create(AssistantApi::class.java)

    @Provides @Singleton
    fun whatsAppApi(retrofit: Retrofit): WhatsAppApi = retrofit.create(WhatsAppApi::class.java)
}
