package com.focusgate.app

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.os.CountDownTimer
import android.text.Editable
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Space
import android.widget.TextView
import android.widget.Toast

class ChallengeActivity : Activity() {
    private lateinit var timerText: TextView
    private lateinit var answerInput: EditText
    private lateinit var phraseInput: EditText
    private lateinit var intentionInput: EditText
    private lateinit var unlockButton: Button

    private lateinit var taskPrompt: String
    private lateinit var answerHint: String
    private lateinit var phrase: String
    private lateinit var answer: String
    private lateinit var intentionTitle: String
    private lateinit var intentionHint: String
    private var waitFinished = false
    private var timer: CountDownTimer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val challenge = savedInstanceState?.let(::challengeFromBundle) ?: ChallengeFactory.newChallenge()
        taskPrompt = challenge.taskPrompt
        answerHint = challenge.answerHint
        phrase = challenge.phrase
        answer = challenge.answer
        intentionTitle = challenge.intentionTitle
        intentionHint = challenge.intentionHint
        setContentView(buildContent(challenge))
        startWaitTimer(challenge.remainingMillis)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("task_prompt", taskPrompt)
        outState.putString("answer_hint", answerHint)
        outState.putString("phrase", phrase)
        outState.putString("answer", answer)
        outState.putString("intention_title", intentionTitle)
        outState.putString("intention_hint", intentionHint)
        outState.putLong("remaining", remainingMillisFromTimerText())
        super.onSaveInstanceState(outState)
    }

    override fun onDestroy() {
        timer?.cancel()
        super.onDestroy()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        goHome()
    }

    private fun buildContent(challenge: ChallengeSpec): View {
        val root = ScrollView(this)
        root.setBackgroundColor(MainActivity.COLOR_CANVAS)

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

        val title = intent.getStringExtra(EXTRA_TITLE) ?: "Unlock requires a task"
        val reason = intent.getStringExtra(EXTRA_REASON)
            ?: "Complete each step to unlock short-form video for ${GatekeeperPolicy.UNLOCK_MINUTES} minutes."

        column.addView(text(title, 30f, MainActivity.COLOR_INK, true))
        column.addView(text(reason, 16f, MainActivity.COLOR_MUTED, false))
        column.addView(space(20))

        timerText = text("", 18f, MainActivity.COLOR_DANGER, true)
        column.addView(panel(timerText))
        column.addView(space(20))

        column.addView(text("1. Random task", 20f, MainActivity.COLOR_INK, true))
        column.addView(text(challenge.taskPrompt, 17f, MainActivity.COLOR_MUTED, false))
        answerInput = input(challenge.answerHint).apply {
            setSingleLine(true)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or
                android.text.InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            imeOptions = EditorInfo.IME_ACTION_NEXT
        }
        column.addView(answerInput)

        column.addView(space(18))
        column.addView(text("2. Type exactly", 20f, MainActivity.COLOR_INK, true))
        column.addView(text(phrase, 17f, MainActivity.COLOR_MUTED, true))
        phraseInput = input("Exact phrase").apply {
            imeOptions = EditorInfo.IME_ACTION_NEXT
        }
        column.addView(phraseInput)

        column.addView(space(18))
        column.addView(text(challenge.intentionTitle, 20f, MainActivity.COLOR_INK, true))
        intentionInput = input(challenge.intentionHint).apply {
            minLines = 2
            gravity = Gravity.TOP
            imeOptions = EditorInfo.IME_ACTION_DONE
        }
        column.addView(intentionInput)

        column.addView(space(22))
        unlockButton = Button(this).apply {
            text = "Unlock ${GatekeeperPolicy.UNLOCK_MINUTES} minutes"
            textSize = 16f
            isAllCaps = false
            setTextColor(MainActivity.COLOR_BUTTON_TEXT)
            background = rounded(MainActivity.COLOR_DISABLED, dp(8).toFloat())
            isEnabled = false
            setPadding(dp(14), dp(12), dp(14), dp(12))
            setOnClickListener { unlock() }
        }
        column.addView(unlockButton)

        val watcher = object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) = Unit
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) = refreshUnlockState()
            override fun afterTextChanged(s: Editable?) = Unit
        }
        answerInput.addTextChangedListener(watcher)
        phraseInput.addTextChangedListener(watcher)
        intentionInput.addTextChangedListener(watcher)

        return root
    }

    private fun startWaitTimer(initialMillis: Long) {
        if (initialMillis <= 0L) {
            waitFinished = true
            timerText.text = "Wait complete"
            refreshUnlockState()
            return
        }

        timer = object : CountDownTimer(initialMillis, 1_000L) {
            override fun onTick(millisUntilFinished: Long) {
                val seconds = (millisUntilFinished / 1000L).coerceAtLeast(1L)
                timerText.text = "Pause for $seconds seconds before unlocking"
            }

            override fun onFinish() {
                waitFinished = true
                timerText.text = "Wait complete"
                refreshUnlockState()
            }
        }.start()
    }

    private fun refreshUnlockState() {
        val answerOk = normalizeTaskAnswer(answerInput.text.toString()) == normalizeTaskAnswer(answer)
        val phraseOk = phraseInput.text.toString() == phrase
        val intentionOk = intentionInput.text.toString().trim().length >= 24
        val ready = waitFinished && answerOk && phraseOk && intentionOk

        unlockButton.isEnabled = ready
        unlockButton.background = rounded(
            if (ready) MainActivity.COLOR_ACCENT else MainActivity.COLOR_DISABLED,
            dp(8).toFloat()
        )
    }

    private fun unlock() {
        GatekeeperPolicy.grantUnlock(this)
        Toast.makeText(
            this,
            "Unlocked for ${GatekeeperPolicy.UNLOCK_MINUTES} minutes",
            Toast.LENGTH_SHORT
        ).show()
        finish()
    }

    private fun normalizeTaskAnswer(value: String): String =
        value
            .trim()
            .lowercase()
            .replace(",", " ")
            .replace(Regex("\\s+"), " ")

    private fun goHome() {
        val home = Intent(Intent.ACTION_MAIN)
            .addCategory(Intent.CATEGORY_HOME)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(home)
        finish()
    }

    private fun challengeFromBundle(bundle: Bundle): ChallengeSpec =
        ChallengeSpec(
            taskPrompt = bundle.getString("task_prompt").orEmpty(),
            answerHint = bundle.getString("answer_hint").orEmpty(),
            phrase = bundle.getString("phrase").orEmpty(),
            answer = bundle.getString("answer").orEmpty(),
            intentionTitle = bundle.getString("intention_title").orEmpty(),
            intentionHint = bundle.getString("intention_hint").orEmpty(),
            remainingMillis = bundle.getLong("remaining", 0L)
        )

    private fun remainingMillisFromTimerText(): Long {
        val digits = timerText.text.filter { it.isDigit() }.toString().toLongOrNull()
        return (digits ?: 0L) * 1_000L
    }

    private fun panel(vararg children: View): View {
        val panel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(18), dp(16), dp(18), dp(16))
            background = rounded(MainActivity.COLOR_PANEL, dp(14).toFloat())
        }
        children.forEach { panel.addView(it) }
        return panel
    }

    private fun input(hintText: String): EditText =
        EditText(this).apply {
            hint = hintText
            textSize = 16f
            setSingleLine(false)
            setTextColor(MainActivity.COLOR_INK)
            setHintTextColor(MainActivity.COLOR_MUTED)
            background = rounded(MainActivity.COLOR_FIELD, dp(8).toFloat()).apply {
                setStroke(dp(1), MainActivity.COLOR_STROKE)
            }
            setPadding(dp(14), dp(12), dp(14), dp(12))
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
        const val EXTRA_TITLE = "title"
        const val EXTRA_REASON = "reason"
        const val EXTRA_PACKAGE = "package"
    }
}
