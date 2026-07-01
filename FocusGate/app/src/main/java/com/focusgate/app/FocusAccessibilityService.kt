package com.focusgate.app

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.util.Locale

class FocusAccessibilityService : AccessibilityService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var lastBlockAtMillis = 0L
    private var lastBlockedPackage: String? = null

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event ?: return

        val packageName = event.packageName?.toString() ?: return
        if (packageName == this.packageName) return
        if (!GatekeeperPolicy.isTargetPackage(packageName)) return
        if (GatekeeperPolicy.isUnlockActive(this)) return

        val now = System.currentTimeMillis()
        if (packageName == lastBlockedPackage && now - lastBlockAtMillis < 2_500L) return

        val visibleText = collectVisibleText(event)
        val normalizedText = visibleText.lowercase(Locale.US)
        if (GatekeeperPolicy.isSharedVideoContext(normalizedText)) {
            GatekeeperPolicy.grantSharedVideoAllowance(this, packageName)
        }

        val decision = GatekeeperPolicy.decisionFor(
            packageName = packageName,
            visibleText = visibleText,
            blockEntireApps = GatekeeperPolicy.isStrictMode(this),
            allowSharedVideo = GatekeeperPolicy.isSharedVideoAllowanceActive(this, packageName)
        ) ?: return

        lastBlockedPackage = packageName
        lastBlockAtMillis = now
        openChallenge(decision)
    }

    override fun onInterrupt() = Unit

    private fun collectVisibleText(event: AccessibilityEvent): String {
        val builder = StringBuilder()
        event.text?.joinTo(builder, separator = " ")
        rootInActiveWindow?.let { root ->
            appendNodeText(root, builder, depth = 0, maxNodes = NodeBudget(260))
        }
        return builder.toString()
    }

    private fun appendNodeText(
        node: AccessibilityNodeInfo,
        builder: StringBuilder,
        depth: Int,
        maxNodes: NodeBudget
    ) {
        if (depth > 12 || !maxNodes.takeOne()) return

        node.text?.let {
            builder.append(' ').append(it)
        }
        node.contentDescription?.let {
            builder.append(' ').append(it)
        }
        node.viewIdResourceName?.let {
            builder.append(' ').append(it)
        }

        for (index in 0 until node.childCount) {
            node.getChild(index)?.let { child ->
                appendNodeText(child, builder, depth + 1, maxNodes)
            }
        }
    }

    private fun openChallenge(decision: GatekeeperPolicy.BlockDecision) {
        val intent = Intent(this, ChallengeActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(ChallengeActivity.EXTRA_TITLE, decision.title)
            .putExtra(ChallengeActivity.EXTRA_REASON, decision.reason)
            .putExtra(ChallengeActivity.EXTRA_PACKAGE, decision.packageName)

        runCatching {
            startActivity(intent)
        }.onFailure {
            performGlobalAction(GLOBAL_ACTION_HOME)
            mainHandler.postDelayed({ startActivity(intent) }, 250L)
        }
    }

    private class NodeBudget(private var remaining: Int) {
        fun takeOne(): Boolean {
            if (remaining <= 0) return false
            remaining -= 1
            return true
        }
    }
}
