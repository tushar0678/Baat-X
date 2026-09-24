package com.baatx.features.settings

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.PhoneCallback
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.baatx.core.calls.CallStateStore
import com.baatx.features.auth.AuthViewModel
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    onOpenAssistant: () -> Unit,
    viewModel: AuthViewModel = hiltViewModel(),
    callSyncViewModel: CallSyncSettingsViewModel = hiltViewModel(),
) {
    val callSyncEnabled by callSyncViewModel.enabled.collectAsStateWithLifecycle()

    // Call sync only turns on once the user has actually granted the
    // permissions; a silent half-working feature would be worse than none.
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) { granted ->
        val canDetectCalls = granted[Manifest.permission.READ_PHONE_STATE] == true
        callSyncViewModel.setEnabled(canDetectCalls)
    }

    Scaffold(topBar = { TopAppBar(title = { Text("More") }) }) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {

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
                        "We don't store your recordings. We extract what matters and update your CRM.",
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
