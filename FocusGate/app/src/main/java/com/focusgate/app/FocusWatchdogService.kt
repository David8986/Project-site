package com.focusgate.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper

class FocusWatchdogService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private var lastBlockAtMillis = 0L
    private var lastBlockedPackage: String? = null
    private var lastForegroundPackage: String? = null

    private val watchdogRunnable = object : Runnable {
        override fun run() {
            runWatchdogTick()
            handler.postDelayed(this, 1_500L)
        }
    }

    override fun onCreate() {
        super.onCreate()
        startForeground(NOTIFICATION_ID, buildNotification())
        handler.post(watchdogRunnable)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        return START_STICKY
    }

    override fun onDestroy() {
        handler.removeCallbacks(watchdogRunnable)
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun runWatchdogTick() {
        if (GatekeeperPolicy.isUnlockActive(this)) return

        val packageName = currentForegroundPackage() ?: return
        if (packageName != lastForegroundPackage) {
            val previousPackage = lastForegroundPackage
            if (
                GatekeeperPolicy.isTargetPackage(packageName) &&
                previousPackage != this.packageName &&
                GatekeeperPolicy.canGrantSharedAllowanceFrom(previousPackage)
            ) {
                GatekeeperPolicy.grantSharedVideoAllowance(this, packageName)
            }
            lastForegroundPackage = packageName
        }

        if (packageName == this.packageName) return
        if (!GatekeeperPolicy.isTargetPackage(packageName)) return

        val now = System.currentTimeMillis()
        if (packageName == lastBlockedPackage && now - lastBlockAtMillis < 4_000L) return

        val decision = GatekeeperPolicy.packageOnlyDecisionFor(
            packageName = packageName,
            blockEntireApps = GatekeeperPolicy.isStrictMode(this)
        ) ?: return

        lastBlockedPackage = packageName
        lastBlockAtMillis = now
        openChallenge(decision)
    }

    private fun currentForegroundPackage(): String? {
        val usageStats = getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val end = System.currentTimeMillis()
        val events = usageStats.queryEvents(end - 10_000L, end)
        val event = UsageEvents.Event()
        var latestPackage: String? = null
        var latestTime = 0L

        while (events.hasNextEvent()) {
            events.getNextEvent(event)
            val isForeground = event.eventType == UsageEvents.Event.MOVE_TO_FOREGROUND ||
                event.eventType == UsageEvents.Event.ACTIVITY_RESUMED
            if (isForeground && event.timeStamp >= latestTime) {
                latestPackage = event.packageName
                latestTime = event.timeStamp
            }
        }

        return latestPackage
    }

    private fun openChallenge(decision: GatekeeperPolicy.BlockDecision) {
        val intent = Intent(this, ChallengeActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            .putExtra(ChallengeActivity.EXTRA_TITLE, decision.title)
            .putExtra(ChallengeActivity.EXTRA_REASON, decision.reason)
            .putExtra(ChallengeActivity.EXTRA_PACKAGE, decision.packageName)

        startActivity(intent)
    }

    private fun buildNotification(): Notification {
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "FocusGate watchdog",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps the short-video blocker active."
            }
            notificationManager.createNotificationChannel(channel)
        }

        val contentIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return Notification.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setContentTitle("FocusGate is active")
            .setContentText("Watching TikTok, YouTube, and Instagram.")
            .setContentIntent(contentIntent)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "focusgate_watchdog"
        private const val NOTIFICATION_ID = 3017

        fun start(context: Context) {
            val intent = Intent(context, FocusWatchdogService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }
    }
}
