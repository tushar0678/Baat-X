package com.baatx.features.org

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import com.baatx.core.network.ApiResult
import com.baatx.core.org.OrgContext
import com.baatx.domain.repository.OrganizationRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class CreateOrganizationUiState(
    val name: String = "",
    val vertical: String = "generic",
    val isSubmitting: Boolean = false,
    val created: Boolean = false,
    val error: String? = null,
) {
    val canSubmit: Boolean
        get() = !isSubmitting && name.trim().length >= 2
}

/** Business verticals the server accepts - kept in sync with BusinessVertical. */
data class VerticalOption(val value: String, val label: String)

val ORGANIZATION_VERTICALS = listOf(
    VerticalOption("real_estate", "Real Estate"),
    VerticalOption("automobile", "Automobile"),
    VerticalOption("retail", "Retail"),
    VerticalOption("services", "Services"),
    VerticalOption("generic", "Other"),
)

@HiltViewModel
class CreateOrganizationViewModel @Inject constructor(
    private val repository: OrganizationRepository,
    private val orgContext: OrgContext,
) : ViewModel() {

    private val _state = MutableStateFlow(CreateOrganizationUiState())
    val state: StateFlow<CreateOrganizationUiState> = _state.asStateFlow()

    fun onNameChange(value: String) {
        _state.value = _state.value.copy(name = value, error = null)
    }

    fun onVerticalChange(value: String) {
        _state.value = _state.value.copy(vertical = value)
    }

    /**
     * Creates the organization, then immediately switches the app into it -
     * a manager who just created a business expects to land inside it, not
     * back on a switcher showing zero organizations.
     */
    fun create() = viewModelScope.launch {
        val current = _state.value
        if (!current.canSubmit) return@launch

        _state.value = current.copy(isSubmitting = true, error = null)

        when (
            val result = repository.createOrganization(
                name = current.name.trim(),
                vertical = current.vertical,
            )
        ) {
            is ApiResult.Success -> {
                orgContext.switchTo(
                    orgId = result.data.id,
                    orgName = result.data.name,
                    role = result.data.role,
                    permissions = result.data.permissions.toSet(),
                )
                _state.value = _state.value.copy(isSubmitting = false, created = true)
            }
            is ApiResult.Failure -> {
                _state.value = _state.value.copy(
                    isSubmitting = false,
                    error = result.error.message,
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateOrganizationScreen(
    onBack: () -> Unit,
    onCreated: () -> Unit,
    viewModel: CreateOrganizationViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    var verticalMenuExpanded by remember { mutableStateOf(false) }

    LaunchedEffect(state.created) {
        if (state.created) onCreated()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("New organization") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                "Set up a new organization to give it its own customers, leads, " +
                    "teams and follow-ups - completely separate from any other " +
                    "organization you belong to.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = state.name,
                onValueChange = viewModel::onNameChange,
                label = { Text("Organization name") },
                placeholder = { Text("e.g. ABC Realty") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Words,
                    imeAction = ImeAction.Done,
                ),
                isError = state.error != null,
                modifier = Modifier.fillMaxWidth(),
            )

            ExposedDropdownMenuBox(
                expanded = verticalMenuExpanded,
                onExpandedChange = { verticalMenuExpanded = it },
            ) {
                OutlinedTextField(
                    value = ORGANIZATION_VERTICALS.first { it.value == state.vertical }.label,
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Business type") },
                    trailingIcon = {
                        ExposedDropdownMenuDefaults.TrailingIcon(expanded = verticalMenuExpanded)
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                )

                ExposedDropdownMenu(
                    expanded = verticalMenuExpanded,
                    onDismissRequest = { verticalMenuExpanded = false },
                ) {
                    ORGANIZATION_VERTICALS.forEach { option ->
                        DropdownMenuItem(
                            text = { Text(option.label) },
                            onClick = {
                                viewModel.onVerticalChange(option.value)
                                verticalMenuExpanded = false
                            },
                        )
                    }
                }
            }

            state.error?.let {
                Text(
                    it,
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }

            Button(
                onClick = viewModel::create,
                enabled = state.canSubmit,
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) {
                if (state.isSubmitting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                } else {
                    Text("Create organization")
                }
            }

            Text(
                "You'll become the owner of this organization and can invite your " +
                    "team, create sub-teams, and assign roles right after.",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
