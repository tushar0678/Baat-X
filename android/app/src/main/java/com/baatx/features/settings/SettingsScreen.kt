package com.baatx.features.settings

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Business
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.PhoneCallback
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.calls.CallStateStore
import com.baatx.core.org.OrgContext
import com.baatx.features.auth.AuthViewModel
import com.baatx.features.org.OrgSwitcherSheet
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

@HiltViewModel
class CallSyncSettingsViewModel @Inject constructor(
    private val callStateStore: CallStateStore,
) : ViewModel() {

    private val _enabled = MutableStateFlow(callStateStore.callSyncEnabled)
    val enabled: StateFlow<Boolean> = _enabled.asStateFlow()

    fun setEnabled(value: Boolean) {
        callStateStore.callSyncEnabled = value
        _enabled.value = value
    }
}

@HiltViewModel
class OrgSettingsViewModel @Inject constructor(
    orgContext: OrgContext,
) : ViewModel() {
    val organizationName: StateFlow<String?> = orgContext.activeOrgName
    val role: StateFlow<String?> = orgContext.role
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onOpenAssistant: () -> Unit,
    onOpenTeams: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
    callSyncViewModel: CallSyncSettingsViewModel = hiltViewModel(),
    orgViewModel: OrgSettingsViewModel = hiltViewModel(),
) {
    val callSyncEnabled by callSyncViewModel.enabled.collectAsStateWithLifecycle()
    val organizationName by orgViewModel.organizationName.collectAsStateWithLifecycle()
    val role by orgViewModel.role.collectAsStateWithLifecycle()

    var showOrgSwitcher by remember { mutableStateOf(false) }

    // Call sync only turns on once the permissions are actually granted; a
    // silently half-working feature would be worse than none.
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { granted ->
        callSyncViewModel.setEnabled(granted[Manifest.permission.READ_PHONE_STATE] == true)
    }

    Scaffold(topBar = { TopAppBar(title = { Text("More") }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {

            ListItem(
                headlineContent = { Text(organizationName ?: "Your organization") },
                supportingContent = { Text(role?.roleLabel() ?: "Tap to switch") },
                leadingContent = { Icon(Icons.Default.Business, contentDescription = null) },
                modifier = Modifier.clickable { showOrgSwitcher = true },
            )
            HorizontalDivider()

            ListItem(
                headlineContent = { Text("Teams & people") },
                supportingContent = { Text("Manage teams, roles and invitations") },
                leadingContent = { Icon(Icons.Default.Groups, contentDescription = null) },
                modifier = Modifier.clickable(onClick = onOpenTeams),
            )
            HorizontalDivider()

            ListItem(
                headlineContent = { Text("Ask BaatX") },
                supportingContent = { Text("Natural-language questions about your CRM") },
                leadingContent = { Icon(Icons.Default.AutoAwesome, contentDescription = null) },
                modifier = Modifier.clickable(onClick = onOpenAssistant),
            )
            HorizontalDivider()

            ListItem(
                headlineContent = { Text("Sync calls automatically") },
                supportingContent = {
                    Text(
                        "After a call ends, BaatX asks if you want to attach its recording. " +
                            "It never records calls and never uploads anything on its own.",
                    )
                },
                leadingContent = { Icon(Icons.Default.PhoneCallback, contentDescription = null) },
                trailingContent = {
                    Switch(
                        checked = callSyncEnabled,
                        onCheckedChange = { wanted ->
                            if (wanted) {
                                permissionLauncher.launch(callSyncPermissions())
                            } else {
                                callSyncViewModel.setEnabled(false)
                            }
                        },
                    )
                },
            )
            HorizontalDivider()

            ListItem(
                headlineContent = { Text("Privacy") },
                supportingContent = {
                    Text(
                        "We don't store your recordings. We extract what matters and " +
                            "update your CRM.",
                    )
                },
                leadingContent = { Icon(Icons.Default.Shield, contentDescription = null) },
            )
            HorizontalDivider()

            viewModel.currentUserName()?.let { name ->
                ListItem(
                    headlineContent = { Text("Signed in as") },
                    supportingContent = { Text(name) },
                )
                HorizontalDivider()
            }

            ListItem(
                headlineContent = { Text("Sign out") },
                leadingContent = {
                    Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null)
                },
                modifier = Modifier.clickable { viewModel.signOut() },
            )

            Spacer(Modifier.weight(1f))
            Text(
                "BaatX 1.0.0 — You talk. BaatX remembers, updates, and reminds.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(16.dp),
            )
        }

        if (showOrgSwitcher) {
            OrgSwitcherSheet(
                onDismiss = { showOrgSwitcher = false },
                onCreateOrganization = { showOrgSwitcher = false },
                // OrgContext's switch listener clears cached data, so there is
                // nothing to do here but close the sheet.
                onSwitched = { showOrgSwitcher = false },
            )
        }
    }
}

private fun callSyncPermissions(): Array<String> = buildList {
    add(Manifest.permission.READ_PHONE_STATE)
    add(Manifest.permission.READ_CALL_LOG)
    add(Manifest.permission.READ_CONTACTS)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        add(Manifest.permission.POST_NOTIFICATIONS)
    }
}.toTypedArray()

private fun String.roleLabel(): String = when (this) {
    "owner" -> "Owner"
    "manager" -> "Manager"
    "team_lead" -> "Team Lead"
    "member" -> "Member"
    "viewer" -> "Viewer"
    else -> replaceFirstChar(Char::uppercase)
}
