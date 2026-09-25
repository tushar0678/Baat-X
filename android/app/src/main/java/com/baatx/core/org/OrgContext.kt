package com.baatx.core.org

import android.content.Context
import androidx.core.content.edit
import com.baatx.core.security.TokenStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * The organization the app is currently showing.
 *
 * Every request carries this id in `X-Organization-Id`, but it is only ever a
 * *request*: the server re-checks membership and refuses if the user doesn't
 * belong. Nothing here grants access - it only decides which organization we
 * are asking about.
 */
@Singleton
class OrgContext @Inject constructor(
    @ApplicationContext context: Context,
    private val tokenStore: TokenStore,
) {

    private val prefs = context.getSharedPreferences("baatx_org", Context.MODE_PRIVATE)

    private val _activeOrgId = MutableStateFlow(
        prefs.getString(KEY_ORG_ID, null) ?: tokenStore.businessId,
    )
    val activeOrgId: StateFlow<String?> = _activeOrgId.asStateFlow()

    private val _activeOrgName = MutableStateFlow(prefs.getString(KEY_ORG_NAME, null))
    val activeOrgName: StateFlow<String?> = _activeOrgName.asStateFlow()

    private val _role = MutableStateFlow(prefs.getString(KEY_ROLE, null))
    val role: StateFlow<String?> = _role.asStateFlow()

    private val _permissions = MutableStateFlow(
        prefs.getStringSet(KEY_PERMISSIONS, emptySet()).orEmpty(),
    )
    val permissions: StateFlow<Set<String>> = _permissions.asStateFlow()

    /** Listeners clear cached CRM data when the organization changes. */
    private val listeners = mutableListOf<() -> Unit>()

    fun addSwitchListener(listener: () -> Unit) {
        listeners += listener
    }

    fun switchTo(orgId: String, orgName: String, role: String, permissions: Set<String>) {
        prefs.edit {
            putString(KEY_ORG_ID, orgId)
            putString(KEY_ORG_NAME, orgName)
            putString(KEY_ROLE, role)
            putStringSet(KEY_PERMISSIONS, permissions)
        }
        _activeOrgId.value = orgId
        _activeOrgName.value = orgName
        _role.value = role
        _permissions.value = permissions

        // Nothing from the previous organization may survive the switch -
        // not in a list, not in a back stack, not in a cache.
        listeners.forEach { it() }
    }

    /**
     * Permissions are mirrored here only to hide buttons the user can't use.
     * Never treat this as a security check: the server decides, every time.
     */
    fun can(permission: String): Boolean = permission in _permissions.value

    fun clear() {
        prefs.edit { clear() }
        _activeOrgId.value = null
        _activeOrgName.value = null
        _role.value = null
        _permissions.value = emptySet()
        listeners.forEach { it() }
    }

    private companion object {
        const val KEY_ORG_ID = "active_org_id"
        const val KEY_ORG_NAME = "active_org_name"
        const val KEY_ROLE = "active_role"
        const val KEY_PERMISSIONS = "active_permissions"
    }
}

object Permissions {
    const val VIEW_TEAM = "view:team"
    const val VIEW_ORG = "view:org"
    const val CUSTOMER_ASSIGN = "customer:assign"
    const val LEAD_ASSIGN = "lead:assign"
    const val FOLLOWUP_ASSIGN = "followup:assign"
    const val TEAM_MANAGE = "team:manage"
    const val USER_MANAGE = "user:manage"
    const val PERMISSION_MANAGE = "permission:manage"
    const val ORG_MANAGE = "org:manage"
    const val REPORT_EXPORT = "report:export"
    const val AUDIT_VIEW = "audit:view"
}
