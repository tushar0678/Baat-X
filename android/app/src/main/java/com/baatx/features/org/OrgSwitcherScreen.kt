package com.baatx.features.org

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Business
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.core.org.OrgContext
import com.baatx.data.remote.dto.OrganizationSummaryDto
import com.baatx.domain.repository.OrganizationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class OrgSwitcherUiState(
    val isLoading: Boolean = true,
    val organizations: List<OrganizationSummaryDto> = emptyList(),
    val isSwitching: Boolean = false,
    val switched: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class OrgSwitcherViewModel @Inject constructor(
    private val repository: OrganizationRepository,
    private val orgContext: OrgContext,
) : ViewModel() {

    private val _state = MutableStateFlow(OrgSwitcherUiState())
    val state: StateFlow<OrgSwitcherUiState> = _state.asStateFlow()

    val activeOrgId: StateFlow<String?> = orgContext.activeOrgId

    init {
        load()
    }

    fun load() = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true)
        _state.value = when (val result = repository.myOrganizations()) {
            is ApiResult.Success ->
                _state.value.copy(isLoading = false, organizations = result.data)
            is ApiResult.Failure ->
                _state.value.copy(isLoading = false, error = result.error.message)
        }
    }

    /**
     * Re-reads the organization from the server rather than trusting the
     * summary we already hold, so role and permissions are always the
     * server's current answer - not a stale copy from the switcher list.
     */
    fun switchTo(organization: OrganizationSummaryDto) = viewModelScope.launch {
        if (organization.id == orgContext.activeOrgId.value) return@launch

        _state.value = _state.value.copy(isSwitching = true, error = null)

        _state.value = when (val result = repository.activate(organization.id)) {
            is ApiResult.Success -> {
                orgContext.switchTo(
                    orgId = result.data.id,
                    orgName = result.data.name,
                    role = result.data.role,
                    permissions = result.data.permissions.toSet(),
                )
                _state.value.copy(isSwitching = false, switched = true)
            }
            is ApiResult.Failure ->
                _state.value.copy(isSwitching = false, error = result.error.message)
        }
    }

    fun consumeSwitch() {
        _state.value = _state.value.copy(switched = false)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrgSwitcherSheet(
    onDismiss: () -> Unit,
    onCreateOrganization: () -> Unit,
    onSwitched: () -> Unit,
    viewModel: OrgSwitcherViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val activeOrgId by viewModel.activeOrgId.collectAsStateWithLifecycle()

    LaunchedEffect(state.switched) {
        if (state.switched) {
            viewModel.consumeSwitch()
            onSwitched()
        }
    }

    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(Modifier.padding(bottom = 32.dp)) {
            Text(
                "Switch organization",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp),
            )

            when {
                state.isLoading -> Box(
                    Modifier.fillMaxWidth().padding(32.dp),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }

                state.organizations.isEmpty() -> Text(
                    "You're not part of any organization yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(20.dp),
                )

                else -> state.organizations.forEach { organization ->
                    ListItem(
                        headlineContent = { Text(organization.name) },
                        supportingContent = { Text(organization.role.roleLabel()) },
                        leadingContent = {
                            Icon(Icons.Default.Business, contentDescription = null)
                        },
                        trailingContent = {
                            if (organization.id == activeOrgId) {
                                Icon(
                                    Icons.Default.Check,
                                    contentDescription = "Current organization",
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                            }
                        },
                        modifier = Modifier.clickable(enabled = !state.isSwitching) {
                            viewModel.switchTo(organization)
                        },
                    )
                }
            }

            if (state.isSwitching) {
                LinearProgressIndicator(Modifier.fillMaxWidth())
            }

            state.error?.let {
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
                )
            }

            HorizontalDivider(Modifier.padding(vertical = 8.dp))

            ListItem(
                headlineContent = { Text("Create new organization") },
                leadingContent = { Icon(Icons.Default.Add, contentDescription = null) },
                modifier = Modifier.clickable(onClick = onCreateOrganization),
            )
        }
    }
}

internal fun String.roleLabel(): String = when (this) {
    "owner" -> "Owner"
    "manager" -> "Manager"
    "team_lead" -> "Team Lead"
    "member" -> "Member"
    "viewer" -> "Viewer"
    else -> replaceFirstChar(Char::uppercase)
}
