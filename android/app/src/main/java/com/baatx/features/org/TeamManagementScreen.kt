package com.baatx.features.org

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.GroupAdd
import androidx.compose.material.icons.filled.PersonAdd
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
import com.baatx.core.org.Permissions
import com.baatx.data.remote.dto.MemberDto
import com.baatx.data.remote.dto.TeamDto
import com.baatx.domain.repository.OrganizationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class TeamManagementUiState(
    val isLoading: Boolean = true,
    val teams: List<TeamDto> = emptyList(),
    val members: List<MemberDto> = emptyList(),
    val canManageTeams: Boolean = false,
    val canManageUsers: Boolean = false,
    val showCreateTeam: Boolean = false,
    val showInvite: Boolean = false,
    val inviteToken: String? = null,
    val error: String? = null,
)

@HiltViewModel
class TeamManagementViewModel @Inject constructor(
    private val repository: OrganizationRepository,
    private val orgContext: OrgContext,
) : ViewModel() {

    private val _state = MutableStateFlow(TeamManagementUiState())
    val state: StateFlow<TeamManagementUiState> = _state.asStateFlow()

    init {
        load()
    }

    /**
     * Refreshes permissions from the server before deciding which buttons to
     * show, then loads teams and members.
     *
     * This matters because login/signup deliberately seed `OrgContext` with
     * an empty permission set (the server enforces every action regardless
     * of what the client shows), and nothing else ever refreshed it. Without
     * this call, `orgContext.can(TEAM_MANAGE)` stayed false forever - even
     * for an owner - and the "New team" / "Invite" actions silently never
     * appeared, though the underlying APIs worked fine.
     */
    fun load() = viewModelScope.launch {
        _state.value = _state.value.copy(isLoading = true, error = null)

        when (val current = repository.current()) {
            is ApiResult.Success -> {
                orgContext.switchTo(
                    orgId = current.data.id,
                    orgName = current.data.name,
                    role = current.data.role,
                    permissions = current.data.permissions.toSet(),
                )
            }
            is ApiResult.Failure -> {
                // Non-fatal: fall back to whatever OrgContext already has
                // rather than blocking the whole screen on this refresh.
            }
        }

        _state.value = _state.value.copy(
            canManageTeams = orgContext.can(Permissions.TEAM_MANAGE),
            canManageUsers = orgContext.can(Permissions.USER_MANAGE),
        )

        val teams = repository.teams()
        val members = repository.members()

        _state.value = _state.value.copy(
            isLoading = false,
            teams = (teams as? ApiResult.Success)?.data.orEmpty(),
            members = (members as? ApiResult.Success)?.data.orEmpty(),
            error = (teams as? ApiResult.Failure)?.error?.message
                ?: (members as? ApiResult.Failure)?.error?.message,
        )
    }

    fun showCreateTeam(show: Boolean) {
        _state.value = _state.value.copy(showCreateTeam = show)
    }

    fun showInvite(show: Boolean) {
        _state.value = _state.value.copy(showInvite = show, inviteToken = null)
    }

    fun createTeam(name: String, leadUserId: String?) = viewModelScope.launch {
        when (val result = repository.createTeam(name, leadUserId)) {
            is ApiResult.Success -> {
                _state.value = _state.value.copy(showCreateTeam = false)
                load()
            }
            is ApiResult.Failure ->
                _state.value = _state.value.copy(error = result.error.message)
        }
    }

    fun invite(contact: String, role: String, teamId: String?) = viewModelScope.launch {
        when (val result = repository.invite(contact, role, teamId)) {
            is ApiResult.Success ->
                // The token is shown once so the manager can share the link.
                _state.value = _state.value.copy(inviteToken = result.data.token)
            is ApiResult.Failure ->
                _state.value = _state.value.copy(error = result.error.message)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TeamManagementScreen(
    onBack: () -> Unit,
    viewModel: TeamManagementViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Teams & people") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (state.canManageUsers) {
                        IconButton(onClick = { viewModel.showInvite(true) }) {
                            Icon(Icons.Default.PersonAdd, contentDescription = "Invite")
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            if (state.canManageTeams) {
                ExtendedFloatingActionButton(
                    onClick = { viewModel.showCreateTeam(true) },
                    icon = { Icon(Icons.Default.GroupAdd, contentDescription = null) },
                    text = { Text("New team") },
                )
            }
        },
    ) { padding ->
        if (state.isLoading) {
            Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) { CircularProgressIndicator() }
            return@Scaffold
        }

        LazyColumn(Modifier.fillMaxSize().padding(padding)) {

            item {
                Text(
                    "Teams",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(20.dp, 16.dp, 20.dp, 8.dp),
                )
            }

            if (state.teams.isEmpty()) {
                item {
                    Text(
                        "No teams yet. Create one to group your salespeople under a team lead.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 20.dp),
                    )
                }
            }

            items(state.teams, key = { it.id }) { team ->
                ListItem(
                    headlineContent = { Text(team.name) },
                    supportingContent = {
                        Text(
                            "${team.memberCount} " +
                                if (team.memberCount == 1) "member" else "members",
                        )
                    },
                )
                HorizontalDivider()
            }

            item {
                Text(
                    "People",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(20.dp, 24.dp, 20.dp, 8.dp),
                )
            }

            items(state.members, key = { it.membershipId }) { member ->
                val team = state.teams.firstOrNull { it.id == member.teamId }
                ListItem(
                    headlineContent = { Text(member.fullName) },
                    supportingContent = {
                        Text(
                            listOfNotNull(
                                member.jobTitle ?: member.role.roleLabel(),
                                team?.name,
                            ).joinToString(" • "),
                        )
                    },
                    trailingContent = { RoleBadge(member.role) },
                )
                HorizontalDivider()
            }
        }

        if (state.showCreateTeam) {
            CreateTeamDialog(
                members = state.members,
                onDismiss = { viewModel.showCreateTeam(false) },
                onCreate = viewModel::createTeam,
            )
        }

        if (state.showInvite) {
            InviteDialog(
                teams = state.teams,
                inviteToken = state.inviteToken,
                onDismiss = { viewModel.showInvite(false) },
                onInvite = viewModel::invite,
            )
        }
    }
}

@Composable
private fun RoleBadge(role: String) {
    val container = when (role) {
        "owner", "manager" -> MaterialTheme.colorScheme.primaryContainer
        "team_lead" -> MaterialTheme.colorScheme.secondaryContainer
        else -> MaterialTheme.colorScheme.surfaceVariant
    }
    Surface(color = container, shape = MaterialTheme.shapes.small) {
        Text(
            role.roleLabel(),
            style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
        )
    }
}

@Composable
private fun CreateTeamDialog(
    members: List<MemberDto>,
    onDismiss: () -> Unit,
    onCreate: (String, String?) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var leadUserId by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New team") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Team name") },
                    placeholder = { Text("North Delhi Sales") },
                    singleLine = true,
                )
                Text("Team lead (optional)", style = MaterialTheme.typography.labelLarge)
                members.take(8).forEach { member ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.clickable {
                            leadUserId = if (leadUserId == member.userId) null else member.userId
                        },
                    ) {
                        RadioButton(
                            selected = leadUserId == member.userId,
                            onClick = {
                                leadUserId =
                                    if (leadUserId == member.userId) null else member.userId
                            },
                        )
                        Text(member.fullName)
                    }
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onCreate(name.trim(), leadUserId) },
                enabled = name.isNotBlank(),
            ) { Text("Create") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    )
}

@Composable
private fun InviteDialog(
    teams: List<TeamDto>,
    inviteToken: String?,
    onDismiss: () -> Unit,
    onInvite: (String, String, String?) -> Unit,
) {
    var contact by remember { mutableStateOf("") }
    var role by remember { mutableStateOf("member") }
    var teamId by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (inviteToken == null) "Invite someone" else "Invitation created") },
        text = {
            if (inviteToken != null) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Share this invite code. It expires in 14 days.")
                    SelectionCard(inviteToken)
                }
                return@AlertDialog
            }

            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(
                    value = contact,
                    onValueChange = { contact = it },
                    label = { Text("Email or phone") },
                    singleLine = true,
                )
                Text("Role", style = MaterialTheme.typography.labelLarge)
                listOf(
                    "member" to "Member",
                    "team_lead" to "Team Lead",
                    "manager" to "Manager",
                    "viewer" to "Viewer (read only)",
                ).forEach { (value, label) ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.clickable { role = value },
                    ) {
                        RadioButton(selected = role == value, onClick = { role = value })
                        Text(label)
                    }
                }
                if (teams.isNotEmpty()) {
                    Text("Team (optional)", style = MaterialTheme.typography.labelLarge)
                    teams.forEach { team ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.clickable {
                                teamId = if (teamId == team.id) null else team.id
                            },
                        ) {
                            RadioButton(
                                selected = teamId == team.id,
                                onClick = { teamId = if (teamId == team.id) null else team.id },
                            )
                            Text(team.name)
                        }
                    }
                }
            }
        },
        confirmButton = {
            if (inviteToken != null) {
                TextButton(onClick = onDismiss) { Text("Done") }
            } else {
                TextButton(
                    onClick = { onInvite(contact.trim(), role, teamId) },
                    enabled = contact.isNotBlank(),
                ) { Text("Send invite") }
            }
        },
        dismissButton = {
            if (inviteToken == null) {
                TextButton(onClick = onDismiss) { Text("Cancel") }
            }
        },
    )
}

@Composable
private fun SelectionCard(text: String) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = MaterialTheme.shapes.small,
    ) {
        SelectionContainer {
            Text(
                text,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.padding(12.dp),
            )
        }
    }
}
