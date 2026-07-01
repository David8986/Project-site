package com.focusgate.app

import android.Manifest
import android.app.AppOpsManager
import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.CompoundButton
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.Switch
import android.widget.TextView

class MainActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var statusText: TextView
    private lateinit var unlockText: TextView
    private lateinit var hardeningText: TextView
    private lateinit var adminButton: Button
    private lateinit var strictSwitch: Switch

    private val refreshRunnable = object : Runnable {
        override fun run() {
            refreshStatus()
            handler.postDelayed(this, 1_000L)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestNotificationPermissionIfNeeded()
        runCatching { FocusWatchdogService.start(this) }
        setContentView(buildContent())
    }

    override fun onResume() {
        super.onResume()
        runCatching { FocusWatchdogService.start(this) }
        refreshStatus()
        handler.post(refreshRunnable)
    }

    override fun onPause() {
        handler.removeCallbacks(refreshRunnable)
        super.onPause()
    }

    private fun buildContent(): View {
        val root = ScrollView(this)
        root.setBackgroundColor(COLOR_CANVAS)

        val column = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(24), dp(36), dp(24), dp(28))
        }
        root.addView(
            column,
            ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
            )
        )

        column.addView(text("FocusGate", 34f, COLOR_INK, true))
        column.addView(text("A friction lock for TikTok, YouTube Shorts, and Instagram Reels.", 16f, COLOR_MUTED, false))
        column.addView(space(24))

        statusText = text("", 18f, COLOR_INK, true)
        unlockText = text("", 16f, COLOR_MUTED, false)
        column.addView(panel(statusText, unlockText))
        column.addView(space(18))

        column.addView(button("Enable Accessibility service") {
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        })
        column.addView(space(10))
        column.addView(button("Test the challenge") {
            startActivity(Intent(this, ChallengeActivity::class.java))
        })
        column.addView(space(10))
        column.addView(button("Lock now") {
            GatekeeperPolicy.clearUnlock(this)
            refreshStatus()
        })
        column.addView(space(10))
        column.addView(button("Open Android app settings") {
            val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                .setData(Uri.fromParts("package", packageName, null))
            startActivity(intent)
        })

        column.addView(space(24))
        column.addView(text("Blocking strength", 20f, COLOR_INK, true))
        column.addView(text("Default mode blocks TikTok outright, then blocks Instagram Reels and YouTube Shorts only when those screens are detected. Shared videos get a short allowance. Turn on full-app blocking only when you want maximum friction.", 15f, COLOR_MUTED, false))
        column.addView(space(10))

        strictSwitch = Switch(this).apply {
            text = "Full-app block YouTube and Instagram"
            textSize = 17f
            setTextColor(COLOR_INK)
            isChecked = GatekeeperPolicy.isStrictMode(this@MainActivity)
            setOnCheckedChangeListener { _: CompoundButton, checked: Boolean ->
                GatekeeperPolicy.setStrictMode(this@MainActivity, checked)
            }
        }
        column.addView(strictSwitch)

        column.addView(space(24))
        column.addView(text("Hardening", 20f, COLOR_INK, true))
        hardeningText = text("", 15f, COLOR_MUTED, false)
        column.addView(hardeningText)
        column.addView(space(10))
        column.addView(button("Open Usage Access") {
            startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        })
        column.addView(space(10))
        column.addView(button("Allow battery unrestricted") {
            requestBatteryExemption()
        })
        column.addView(space(10))
        adminButton = button("Enable uninstall friction") {
            toggleDeviceAdmin()
        }
        column.addView(adminButton)

        column.addView(space(24))
        column.addView(text("How it works", 20f, COLOR_INK, true))
        column.addView(text("FocusGate uses Android Accessibility. It reads visible UI text from supported apps locally, then opens a challenge when short-form video is detected. It is a self-control app, not a parental-control system: disabling Accessibility bypasses it, and uninstall friction only adds an extra settings step.", 15f, COLOR_MUTED, false))

        return root
    }

    private fun refreshStatus() {
        val enabled = isAccessibilityServiceEnabled()
        statusText.text = if (enabled) {
            "Blocker is active"
        } else {
            "Blocker is not enabled"
        }
        statusText.setTextColor(if (enabled) COLOR_GOOD else COLOR_DANGER)

        unlockText.text = GatekeeperPolicy.formatRemaining(
            GatekeeperPolicy.remainingUnlockMillis(this)
        )
        strictSwitch.isChecked = GatekeeperPolicy.isStrictMode(this)

        val usageStatus = if (hasUsageAccess()) "on" else "off"
        val batteryStatus = if (isIgnoringBatteryOptimizations()) "unrestricted" else "normal"
        val adminStatus = if (isDeviceAdminActive()) "on" else "off"
        hardeningText.text = "Watchdog service: active\nUsage Access: $usageStatus\nBattery: $batteryStatus\nUninstall friction: $adminStatus"
        adminButton.text = if (isDeviceAdminActive()) {
            "Disable uninstall friction"
        } else {
            "Enable uninstall friction"
        }
    }

    private fun isAccessibilityServiceEnabled(): Boolean {
        val expected = ComponentName(this, FocusAccessibilityService::class.java).flattenToString()
        val enabledServices = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        ) ?: return false

        val splitter = TextUtils.SimpleStringSplitter(':')
        splitter.setString(enabledServices)
        for (service in splitter) {
            if (service.equals(expected, ignoreCase = true)) return true
        }
        return false
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 4001)
        }
    }

    private fun hasUsageAccess(): Boolean {
        val appOps = getSystemService(Context.APP_OPS_SERVICE) as AppOpsManager
        val mode = appOps.checkOpNoThrow(
            AppOpsManager.OPSTR_GET_USAGE_STATS,
            android.os.Process.myUid(),
            packageName
        )
        return mode == AppOpsManager.MODE_ALLOWED
    }

    private fun isIgnoringBatteryOptimizations(): Boolean {
        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        return powerManager.isIgnoringBatteryOptimizations(packageName)
    }

    private fun requestBatteryExemption() {
        if (isIgnoringBatteryOptimizations()) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            return
        }

        val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            .setData(Uri.parse("package:$packageName"))
        startActivity(intent)
    }

    private fun adminComponent(): ComponentName =
        ComponentName(this, FocusDeviceAdminReceiver::class.java)

    private fun isDeviceAdminActive(): Boolean {
        val devicePolicyManager = getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        return devicePolicyManager.isAdminActive(adminComponent())
    }

    private fun toggleDeviceAdmin() {
        val devicePolicyManager = getSystemService(Context.DEVICE_POLICY_SERVICE) as DevicePolicyManager
        val admin = adminComponent()
        if (devicePolicyManager.isAdminActive(admin)) {
            devicePolicyManager.removeActiveAdmin(admin)
            refreshStatus()
            return
        }

        val intent = Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN)
            .putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, admin)
            .putExtra(
                DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "This adds one more settings step before FocusGate can be uninstalled."
            )
        startActivity(intent)
    }

    private fun panel(vararg children: View): View {
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(16))
            background = rounded(COLOR_PANEL, dp(14).toFloat())
        }
        children.forEach { panel.addView(it) }
        return panel
    }

    private fun button(label: String, onClick: () -> Unit): Button =
        Button(this).apply {
            text = label
            textSize = 15f
            isAllCaps = false
            setTextColor(COLOR_BUTTON_TEXT)
            background = rounded(COLOR_ACCENT, dp(8).toFloat())
            setPadding(dp(14), dp(10), dp(14), dp(10))
            setOnClickListener { onClick() }
        }

    private fun text(value: String, sizeSp: Float, color: Int, bold: Boolean): TextView =
        TextView(this).apply {
            text = value
            textSize = sizeSp
            setTextColor(color)
            includeFontPadding = true
            if (bold) typeface = android.graphics.Typeface.DEFAULT_BOLD
            setLineSpacing(2f, 1.05f)
        }

    private fun space(heightDp: Int): View =
        Space(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(heightDp)
            )
        }

    companion object {
        const val COLOR_CANVAS = 0xFF0E1514.toInt()
        const val COLOR_PANEL = 0xFF17211F.toInt()
        const val COLOR_FIELD = 0xFF111B19.toInt()
        const val COLOR_STROKE = 0xFF31413D.toInt()
        const val COLOR_INK = 0xFFF2F7F4.toInt()
        const val COLOR_MUTED = 0xFFA7B5AF.toInt()
        const val COLOR_ACCENT = 0xFF36B8A5.toInt()
        const val COLOR_BUTTON_TEXT = 0xFF06110F.toInt()
        const val COLOR_DISABLED = 0xFF5E6A66.toInt()
        const val COLOR_GOOD = 0xFF59D6A7.toInt()
        const val COLOR_DANGER = 0xFFFF716A.toInt()
    }
}

fun Activity.dp(value: Int): Int =
    (value * resources.displayMetrics.density).toInt()

fun rounded(color: Int, radius: Float): android.graphics.drawable.GradientDrawable =
    android.graphics.drawable.GradientDrawable().apply {
        setColor(color)
        cornerRadius = radius
    }
