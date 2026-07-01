package com.focusgate.app

import kotlin.random.Random

data class ChallengeSpec(
    val taskPrompt: String,
    val answer: String,
    val answerHint: String,
    val phrase: String,
    val intentionTitle: String,
    val intentionHint: String,
    val remainingMillis: Long
)

object ChallengeFactory {
    private const val WAIT_MILLIS = 45_000L

    private val wordPool = listOf(
        "anchor", "brisk", "copper", "delta", "ember", "focus", "garden",
        "harbor", "index", "jungle", "kernel", "ladder", "matrix", "north",
        "orbit", "pencil", "quartz", "ripple", "signal", "timber", "umbra",
        "velvet", "window", "yellow", "zenith", "canvas", "direct", "engine",
        "filter", "ground", "honest", "island", "method", "number", "planet",
        "reason", "stable", "thread", "useful", "winter"
    )

    private val phraseTemplates = listOf(
        "I choose effort before scrolling %s",
        "One useful action comes first %s",
        "This unlock is only five minutes %s",
        "I am making this inconvenient %s",
        "Pause, decide, then continue %s",
        "No automatic scrolling right now %s",
        "I will spend attention on purpose %s",
        "Short videos can wait for work %s"
    )

    private val intentionPrompts = listOf(
        "3. Write the next useful action",
        "3. Name what you will do after this",
        "3. Commit to one real task",
        "3. Write a concrete next step"
    )

    private val intentionHints = listOf(
        "Example: finish physics problem 4 before opening videos",
        "Example: read two pages and make three notes",
        "Example: clean the desk for five minutes first",
        "Example: finish the message I have been avoiding"
    )

    fun newChallenge(): ChallengeSpec {
        val task = randomTask()
        return ChallengeSpec(
            taskPrompt = task.prompt,
            answer = task.answer,
            answerHint = task.hint,
            phrase = randomPhrase(),
            intentionTitle = intentionPrompts.randomItem(),
            intentionHint = intentionHints.randomItem(),
            remainingMillis = WAIT_MILLIS
        )
    }

    private fun randomTask(): Task =
        when (Random.nextInt(12)) {
            0 -> arithmeticTask()
            1 -> sequenceTask()
            2 -> descendingSequenceTask()
            3 -> sortNumbersTask()
            4 -> reverseCodeTask()
            5 -> letterCountTask()
            6 -> initialsTask()
            7 -> oddSumTask()
            8 -> alphabeticalTask()
            9 -> digitTransformTask()
            10 -> rangeDifferenceTask()
            else -> wordLengthTask()
        }

    private fun arithmeticTask(): Task {
        val a = Random.nextInt(17, 67)
        val b = Random.nextInt(13, 49)
        val c = Random.nextInt(4, 16)
        val result = a * b + c * c - a
        return Task(
            prompt = "Calculate without a calculator:\n($a x $b) + ($c x $c) - $a",
            answer = result.toString(),
            hint = "Answer"
        )
    }

    private fun sequenceTask(): Task {
        val start = Random.nextInt(8, 55)
        val step = Random.nextInt(4, 14)
        val sequence = (0..4).map { start + it * step }
        return Task(
            prompt = "Complete the sequence:\n${sequence.take(4).joinToString(", ")}, ?",
            answer = sequence.last().toString(),
            hint = "Missing number"
        )
    }

    private fun descendingSequenceTask(): Task {
        val start = Random.nextInt(75, 140)
        val step = Random.nextInt(5, 17)
        val sequence = (0..4).map { start - it * step }
        return Task(
            prompt = "Complete the descending sequence:\n${sequence.take(4).joinToString(", ")}, ?",
            answer = sequence.last().toString(),
            hint = "Missing number"
        )
    }

    private fun sortNumbersTask(): Task {
        val numbers = List(5) { Random.nextInt(10, 99) }
        return Task(
            prompt = "Type these numbers from smallest to largest, separated by spaces:\n${numbers.joinToString(", ")}",
            answer = numbers.sorted().joinToString(" "),
            hint = "Example: 12 24 39"
        )
    }

    private fun reverseCodeTask(): Task {
        val code = randomCode(7)
        return Task(
            prompt = "Type this code backwards:\n$code",
            answer = code.reversed(),
            hint = "Backwards code"
        )
    }

    private fun letterCountTask(): Task {
        val words = randomWords(9)
        val sentence = words.joinToString(" ")
        val letter = listOf('a', 'e', 'i', 'o', 'r', 's', 't').randomItem()
        return Task(
            prompt = "How many times does the letter '$letter' appear in this line?\n$sentence",
            answer = sentence.count { it == letter }.toString(),
            hint = "Count"
        )
    }

    private fun initialsTask(): Task {
        val words = randomWords(6)
        return Task(
            prompt = "Type the first letter of each word as one lowercase code:\n${words.joinToString(" ")}",
            answer = words.joinToString("") { it.first().toString() },
            hint = "Lowercase code"
        )
    }

    private fun oddSumTask(): Task {
        val numbers = List(7) { Random.nextInt(10, 80) }
        return Task(
            prompt = "Add only the odd numbers:\n${numbers.joinToString(", ")}",
            answer = numbers.filter { it % 2 == 1 }.sum().toString(),
            hint = "Odd-number sum"
        )
    }

    private fun alphabeticalTask(): Task {
        val words = wordPool.shuffled().take(5)
        return Task(
            prompt = "Type the word that comes first alphabetically:\n${words.joinToString(", ")}",
            answer = words.minOrNull().orEmpty(),
            hint = "First alphabetically"
        )
    }

    private fun digitTransformTask(): Task {
        val number = Random.nextInt(20_000, 99_999)
        val multiplier = Random.nextInt(2, 5)
        val digitSum = number.toString().sumOf { it.digitToInt() }
        return Task(
            prompt = "Add the digits of $number, then multiply by $multiplier.",
            answer = (digitSum * multiplier).toString(),
            hint = "Final number"
        )
    }

    private fun rangeDifferenceTask(): Task {
        val numbers = List(6) { Random.nextInt(15, 130) }
        val difference = numbers.maxOrNull().orEmptyInt() - numbers.minOrNull().orEmptyInt()
        return Task(
            prompt = "Find the difference between the largest and smallest number:\n${numbers.joinToString(", ")}",
            answer = difference.toString(),
            hint = "Largest minus smallest"
        )
    }

    private fun wordLengthTask(): Task {
        val words = randomWords(4)
        return Task(
            prompt = "Add the letter counts of these words:\n${words.joinToString(", ")}",
            answer = words.sumOf { it.length }.toString(),
            hint = "Total letters"
        )
    }

    private fun randomPhrase(): String {
        val code = "${randomCode(2)}-${Random.nextInt(100, 999)}"
        return phraseTemplates.randomItem().format(code)
    }

    private fun randomWords(count: Int): List<String> =
        wordPool.shuffled().take(count)

    private fun randomCode(length: Int): String {
        val chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return buildString {
            repeat(length) {
                append(chars[Random.nextInt(chars.length)])
            }
        }
    }

    private data class Task(
        val prompt: String,
        val answer: String,
        val hint: String
    )

    private fun <T> List<T>.randomItem(): T = this[Random.nextInt(size)]

    private fun Int?.orEmptyInt(): Int = this ?: 0
}
