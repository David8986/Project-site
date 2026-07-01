package com.focusgate.app

import android.content.Context
import android.content.SharedPreferences
import java.util.Locale

object GatekeeperPolicy {
    const val UNLOCK_MINUTES = 5L

    private const val PREFS_NAME = "focus_gate"
    private const val KEY_UNLOCK_UNTIL = "unlock_until"
    private const val KEY_FULL_APP_BLOCK = "full_app_block"
    private const val KEY_SHARED_ALLOW_PREFIX = "shared_allow_until_"
    private const val SHARED_ALLOW_MILLIS = 2 * 60_000L

    private val tiktokPackages = setOf(
        "com.zhiliaoapp.musically",
        "com.zhiliaoapp.musically.go",
        "com.ss.android.ugc.trill"
    )

    private val youtubePackages = setOf(
        "com.google.android.youtube",
        "com.google.android.apps.youtube.kids"
    )

    private val instagramPackages = setOf(
        "com.instagram.android"
    )

    private val launcherPackages = setOf(
        "com.google.android.apps.nexuslauncher",
        "com.android.launcher",
        "com.android.launcher3",
        "com.miui.home",
        "com.sec.android.app.launcher",
        "com.oppo.launcher",
        "com.huawei.android.launcher"
    )

    private val likelyMessagePackages = setOf(
        "com.whatsapp",
        "com.whatsapp.w4b",
        "org.telegram.messenger",
        "org.thunderdog.challegram",
        "com.facebook.orca",
        "com.facebook.mlite",
        "com.google.android.apps.messaging",
        "com.samsung.android.messaging",
        "com.discord",
        "com.snapchat.android",
        "com.viber.voip",
        "jp.naver.line.android",
        "com.google.android.gm"
    )

    private val shortsSignals = listOf(
        "create a short",
        "shorts camera",
        "shorts player",
        "shorts_video",
        "shorts_surface",
        "shorts_pivot",
        "shorts_watch",
        "shorts engagement",
        "youtube shorts player"
    )

    private val reelsSignals = listOf(
        "clips viewer",
        "clips_viewer",
        "clips_viewer_root",
        "clips audio",
        "original audio",
        "use template",
        "remix",
        "reels viewer",
        "reels camera",
        "reel_viewer",
        "reel_watch"
    )

    private val sharedVideoSignals = listOf(
        "direct",
        "inbox",
        "message",
        "messages",
        "chat",
        "reply",
        "sent you",
        "sent a reel",
        "shared a reel",
        "shared with you",
        "send message",
        "open in chat",
        "instagram direct",
        "dm"
    )

    data class BlockDecision(
        val title: String,
        val reason: String,
        val packageName: String
    )

    fun prefs(context: Context): SharedPreferences =
        context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    fun isStrictMode(context: Context): Boolean =
        prefs(context).getBoolean(KEY_FULL_APP_BLOCK, false)

    fun setStrictMode(context: Context, enabled: Boolean) {
        prefs(context).edit().putBoolean(KEY_FULL_APP_BLOCK, enabled).apply()
    }

    fun grantUnlock(context: Context, minutes: Long = UNLOCK_MINUTES) {
        val until = System.currentTimeMillis() + minutes * 60_000L
        prefs(context).edit().putLong(KEY_UNLOCK_UNTIL, until).apply()
    }

    fun clearUnlock(context: Context) {
        prefs(context).edit().remove(KEY_UNLOCK_UNTIL).apply()
    }

    fun remainingUnlockMillis(context: Context): Long {
        val until = prefs(context).getLong(KEY_UNLOCK_UNTIL, 0L)
        return (until - System.currentTimeMillis()).coerceAtLeast(0L)
    }

    fun isUnlockActive(context: Context): Boolean = remainingUnlockMillis(context) > 0L

    fun isTargetPackage(packageName: String?): Boolean {
        if (packageName == null) return false
        return packageName in tiktokPackages ||
            packageName in youtubePackages ||
            packageName in instagramPackages
    }

    fun canGrantSharedAllowanceFrom(packageName: String?): Boolean {
        if (packageName == null) return false
        if (packageName in launcherPackages) return false
        if (isTargetPackage(packageName)) return false
        return packageName in likelyMessagePackages || packageName.contains("messag", ignoreCase = true)
    }

    fun grantSharedVideoAllowance(context: Context, packageName: String) {
        if (packageName in tiktokPackages) return
        if (!isTargetPackage(packageName)) return
        prefs(context)
            .edit()
            .putLong(KEY_SHARED_ALLOW_PREFIX + packageName, System.currentTimeMillis() + SHARED_ALLOW_MILLIS)
            .apply()
    }

    fun isSharedVideoAllowanceActive(context: Context, packageName: String?): Boolean {
        if (packageName == null) return false
        val until = prefs(context).getLong(KEY_SHARED_ALLOW_PREFIX + packageName, 0L)
        return until > System.currentTimeMillis()
    }

    fun decisionFor(
        packageName: String?,
        visibleText: String,
        blockEntireApps: Boolean,
        allowSharedVideo: Boolean = false
    ): BlockDecision? {
        if (packageName == null) return null

        val normalizedText = visibleText.lowercase(Locale.US)
        return when {
            packageName in tiktokPackages -> BlockDecision(
                title = "TikTok is locked",
                reason = "TikTok is always gated by FocusGate.",
                packageName = packageName
            )

            packageName in youtubePackages && blockEntireApps -> BlockDecision(
                title = "YouTube is locked",
                reason = "Full-app blocking is enabled for YouTube.",
                packageName = packageName
            )

            packageName in youtubePackages && allowSharedVideo -> null

            packageName in youtubePackages && shortsSignals.any { it in normalizedText } -> BlockDecision(
                title = "YouTube Shorts is locked",
                reason = "FocusGate detected Shorts text on the current YouTube screen.",
                packageName = packageName
            )

            packageName in instagramPackages && blockEntireApps -> BlockDecision(
                title = "Instagram is locked",
                reason = "Full-app blocking is enabled for Instagram.",
                packageName = packageName
            )

            packageName in instagramPackages && isSharedVideoContext(normalizedText) -> null

            packageName in instagramPackages && allowSharedVideo -> null

            packageName in instagramPackages && reelsSignals.any { it in normalizedText } -> BlockDecision(
                title = "Instagram Reels is locked",
                reason = "FocusGate detected Reels-like text on the current Instagram screen.",
                packageName = packageName
            )

            else -> null
        }
    }

    fun packageOnlyDecisionFor(
        packageName: String?,
        blockEntireApps: Boolean
    ): BlockDecision? {
        if (packageName == null) return null

        return when {
            packageName in tiktokPackages -> BlockDecision(
                title = "TikTok is locked",
                reason = "The watchdog detected TikTok in the foreground.",
                packageName = packageName
            )

            packageName in youtubePackages && blockEntireApps -> BlockDecision(
                title = "YouTube is locked",
                reason = "Full-app blocking is enabled for YouTube.",
                packageName = packageName
            )

            packageName in instagramPackages && blockEntireApps -> BlockDecision(
                title = "Instagram is locked",
                reason = "Full-app blocking is enabled for Instagram.",
                packageName = packageName
            )

            else -> null
        }
    }

    fun isSharedVideoContext(normalizedText: String): Boolean =
        sharedVideoSignals.any { it in normalizedText }

    fun formatRemaining(millis: Long): String {
        if (millis <= 0L) return "Blocked now"
        val totalSeconds = millis / 1000L
        val minutes = totalSeconds / 60L
        val seconds = totalSeconds % 60L
        return "Next block in %d:%02d".format(Locale.US, minutes, seconds)
    }
}
