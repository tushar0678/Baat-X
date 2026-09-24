package com.baatx.core.security

import android.content.Context
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Tokens live in EncryptedSharedPreferences, whose master key is held in the
 * Android Keystore (hardware-backed where available). They are never written to
 * logs, backups or plain preferences.
 */
@Singleton
class TokenStore @Inject constructor(@ApplicationContext context: Context) {

    private val prefs by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        EncryptedSharedPreferences.create(
            context,
            "baatx_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    private val _isSignedIn = MutableStateFlow(false)
    val isSignedIn: StateFlow<Boolean> = _isSignedIn

    init {
        _isSignedIn.value = accessToken != null
    }

    val accessToken: String? get() = prefs.getString(KEY_ACCESS, null)
    val refreshToken: String? get() = prefs.getString(KEY_REFRESH, null)
    val businessId: String? get() = prefs.getString(KEY_BUSINESS, null)
    val userName: String? get() = prefs.getString(KEY_USER_NAME, null)

    fun save(access: String, refresh: String, businessId: String?, userName: String?) {
        prefs.edit()
            .putString(KEY_ACCESS, access)
            .putString(KEY_REFRESH, refresh)
            .putString(KEY_BUSINESS, businessId)
            .putString(KEY_USER_NAME, userName)
            .apply()
        _isSignedIn.value = true
    }

    fun updateAccess(access: String, refresh: String?) {
        val editor = prefs.edit().putString(KEY_ACCESS, access)
        if (refresh != null) editor.putString(KEY_REFRESH, refresh)
        editor.apply()
    }

    fun setActiveBusiness(businessId: String) {
        prefs.edit().putString(KEY_BUSINESS, businessId).apply()
    }

    fun clear() {
        prefs.edit().clear().apply()
        _isSignedIn.value = false
    }

    private companion object {
        const val KEY_ACCESS = "access_token"
        const val KEY_REFRESH = "refresh_token"
        const val KEY_BUSINESS = "business_id"
        const val KEY_USER_NAME = "user_name"
    }
}
