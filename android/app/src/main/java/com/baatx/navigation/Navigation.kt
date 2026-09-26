package com.baatx.navigation

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.People
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.baatx.features.assistant.AssistantScreen
import com.baatx.features.auth.AuthViewModel
import com.baatx.features.auth.LoginScreen
import com.baatx.features.callsync.CallSyncScreen
import com.baatx.features.customers.CustomerDetailScreen
import com.baatx.features.customers.CustomersScreen
import com.baatx.features.followups.FollowUpsScreen
import com.baatx.features.home.HomeScreen
import com.baatx.features.org.CreateOrganizationScreen
import com.baatx.features.org.TeamManagementScreen
import com.baatx.features.reports.ReportsScreen
import com.baatx.features.settings.SettingsScreen
import com.baatx.features.tellai.AiReviewScreen
import com.baatx.features.tellai.TellAiScreen

object Routes {
    const val LOGIN = "login"
    const val HOME = "home"
    const val CUSTOMERS = "customers"
    const val CUSTOMER_DETAIL = "customers/{customerId}"
    const val FOLLOW_UPS = "follow-ups"
    const val REPORTS = "reports"
    const val MORE = "more"
    const val TELL_AI = "tell-ai"
    const val REVIEW = "review/{jobId}"
    const val ASSISTANT = "assistant"
    const val CALL_SYNC = "call-sync/{callId}"
    const val TEAMS = "teams"
    const val CREATE_ORGANIZATION = "create-organization"

    fun customerDetail(id: String) = "customers/$id"
    fun review(jobId: String) = "review/$jobId"
    fun callSync(callId: String) = "call-sync/$callId"
}

private data class BottomTab(val route: String, val label: String, val icon: ImageVector)

private val BOTTOM_TABS = listOf(
    BottomTab(Routes.HOME, "Home", Icons.Default.Home),
    BottomTab(Routes.CUSTOMERS, "Customers", Icons.Default.People),
    BottomTab(Routes.FOLLOW_UPS, "Follow-ups", Icons.AutoMirrored.Filled.List),
    BottomTab(Routes.REPORTS, "Reports", Icons.Default.BarChart),
    BottomTab(Routes.MORE, "More", Icons.Default.MoreHoriz),
)

@Composable
fun BaatXApp(
    pendingCallId: String? = null,
    onPendingCallConsumed: () -> Unit = {},
    authViewModel: AuthViewModel = hiltViewModel(),
) {
    val isSignedIn by authViewModel.isSignedIn.collectAsStateWithLifecycle()
    val navController = rememberNavController()

    if (!isSignedIn) {
        LoginScreen(viewModel = authViewModel)
        return
    }

    SignedInScaffold(
        navController = navController,
        pendingCallId = pendingCallId,
        onPendingCallConsumed = onPendingCallConsumed,
    )
}

@Composable
private fun SignedInScaffold(
    navController: NavHostController,
    pendingCallId: String?,
    onPendingCallConsumed: () -> Unit,
) {
    val backStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = backStackEntry?.destination

    // Tapping the "call ended" notification lands the user straight on the
    // sync screen for that call.
    LaunchedEffect(pendingCallId) {
        pendingCallId?.let {
            navController.navigate(Routes.callSync(it)) { launchSingleTop = true }
            onPendingCallConsumed()
        }
    }

    val showChrome = BOTTOM_TABS.any { tab ->
        currentRoute?.hierarchy?.any { it.route == tab.route } == true
    }

    Scaffold(
        bottomBar = {
            if (showChrome) {
                NavigationBar {
                    BOTTOM_TABS.forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute?.hierarchy?.any { it.route == tab.route } == true,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
        floatingActionButton = {
            // Tell AI is the primary action and stays prominent everywhere.
            if (showChrome) {
                ExtendedFloatingActionButton(
                    onClick = { navController.navigate(Routes.TELL_AI) },
                    icon = { Icon(Icons.Default.Mic, contentDescription = null) },
                    text = { Text("Tell AI") },
                )
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            NavHost(navController = navController, startDestination = Routes.HOME) {

                composable(Routes.HOME) {
                    HomeScreen(
                        onTellAi = { navController.navigate(Routes.TELL_AI) },
                        onOpenFollowUps = { navController.navigate(Routes.FOLLOW_UPS) },
                        onOpenCustomer = { navController.navigate(Routes.customerDetail(it)) },
                        onJobStarted = { navController.navigate(Routes.review(it)) },
                    )
                }

                composable(Routes.CUSTOMERS) {
                    CustomersScreen(
                        onOpenCustomer = { navController.navigate(Routes.customerDetail(it)) },
                    )
                }

                composable(Routes.CUSTOMER_DETAIL) { entry ->
                    CustomerDetailScreen(
                        customerId = entry.arguments?.getString("customerId").orEmpty(),
                        onBack = { navController.popBackStack() },
                    )
                }

                composable(Routes.FOLLOW_UPS) {
                    FollowUpsScreen(
                        onOpenCustomer = { navController.navigate(Routes.customerDetail(it)) },
                    )
                }

                composable(Routes.REPORTS) { ReportsScreen() }

                composable(Routes.MORE) {
                    SettingsScreen(
                        onOpenAssistant = { navController.navigate(Routes.ASSISTANT) },
                        onOpenTeams = { navController.navigate(Routes.TEAMS) },
                        onCreateOrganization = {
                            navController.navigate(Routes.CREATE_ORGANIZATION)
                        },
                    )
                }

                composable(Routes.TEAMS) {
                    TeamManagementScreen(onBack = { navController.popBackStack() })
                }

                composable(Routes.CREATE_ORGANIZATION) {
                    CreateOrganizationScreen(
                        onBack = { navController.popBackStack() },
                        onCreated = {
                            // A brand-new organization has no customers or teams
                            // yet, so land on Home rather than back on Settings.
                            navController.navigate(Routes.HOME) {
                                popUpTo(Routes.HOME) { inclusive = true }
                            }
                        },
                    )
                }

                composable(Routes.ASSISTANT) {
                    AssistantScreen(onBack = { navController.popBackStack() })
                }

                composable(Routes.TELL_AI) {
                    TellAiScreen(
                        onBack = { navController.popBackStack() },
                        onJobStarted = { jobId ->
                            navController.navigate(Routes.review(jobId)) {
                                popUpTo(Routes.TELL_AI) { inclusive = true }
                            }
                        },
                    )
                }

                composable(Routes.CALL_SYNC) { entry ->
                    CallSyncScreen(
                        callId = entry.arguments?.getString("callId").orEmpty(),
                        onBack = {
                            if (!navController.popBackStack()) {
                                navController.navigate(Routes.HOME)
                            }
                        },
                        onJobStarted = { jobId ->
                            navController.navigate(Routes.review(jobId)) {
                                popUpTo(Routes.CALL_SYNC) { inclusive = true }
                            }
                        },
                    )
                }

                composable(Routes.REVIEW) { entry ->
                    AiReviewScreen(
                        jobId = entry.arguments?.getString("jobId").orEmpty(),
                        onDone = {
                            navController.navigate(Routes.HOME) {
                                popUpTo(Routes.HOME) { inclusive = true }
                            }
                        },
                        onBack = { navController.popBackStack() },
                    )
                }
            }
        }
    }
}
