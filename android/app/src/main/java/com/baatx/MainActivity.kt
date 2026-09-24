package com.baatx

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import com.baatx.core.ui.BaatXTheme
import com.baatx.navigation.BaatXApp
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    /**
     * Set when the user taps the "sync this call?" notification. Read once by
     * the navigation graph, then cleared so a config change doesn't reopen it.
     */
    private var pendingCallId by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        pendingCallId = intent?.callIdExtra()

        setContent {
            BaatXTheme {
                BaatXApp(
                    pendingCallId = pendingCallId,
                    onPendingCallConsumed = { pendingCallId = null },
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // launchMode=singleTask: an already-running BaatX gets the tap here.
        intent.callIdExtra()?.let { pendingCallId = it }
    }

    private fun Intent.callIdExtra(): String? =
        if (action == ACTION_OPEN_CALL_SYNC) getStringExtra(EXTRA_CALL_ID) else null

    companion object {
        const val ACTION_OPEN_CALL_SYNC = "com.baatx.action.OPEN_CALL_SYNC"
        const val EXTRA_CALL_ID = "baatx_call_id"
    }
}
