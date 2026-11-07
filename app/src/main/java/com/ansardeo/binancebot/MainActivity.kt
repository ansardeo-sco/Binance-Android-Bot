
package com.ansardeo.binancebot

import android.os.Bundle
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class MainActivity : AppCompatActivity() {

    private val baseUrl =
        "https://ansardeo-sco-binance-android-bot.hf.space/api/v1"

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .build()

    private val bg = Color.rgb(8, 15, 29)
    private val card = Color.rgb(17, 29, 47)
    private val yellow = Color.rgb(240, 185, 11)
    private val white = Color.WHITE
    private val muted = Color.rgb(143, 163, 189)
    private val green = Color.rgb(83, 198, 140)
    private val red = Color.rgb(240, 91, 103)

    private lateinit var content: FrameLayout
    private lateinit var topStatus: TextView

    private val symbols = arrayOf(
        "BTCUSDT", "ETHUSDT", "BNBUSDT",
        "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT"
    )

    private var selectedSymbol = "BTCUSDT"
    private var currentPage = "Dashboard"

    private lateinit var navItems: List<TextView>

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        content = findViewById(R.id.contentFrame)
        topStatus = findViewById(R.id.txtTopStatus)

        navItems = listOf(
            findViewById(R.id.navDashboard),
            findViewById(R.id.navPositions),
            findViewById(R.id.navSettings),
            findViewById(R.id.navActivity),
            findViewById(R.id.navMore)
        )

        navItems[0].setOnClickListener { showPage("Dashboard") }
        navItems[1].setOnClickListener { showPage("Positions") }
        navItems[2].setOnClickListener { showPage("Settings") }
        navItems[3].setOnClickListener { showPage("Activity") }
        navItems[4].setOnClickListener { showPage("More") }

        showPage("Dashboard")
    }

    private fun dp(value: Int): Int =
        (value * resources.displayMetrics.density).toInt()

    private fun rounded(color: Int, radius: Int = 16): GradientDrawable {
        return GradientDrawable().apply {
            setColor(color)
            cornerRadius = dp(radius).toFloat()
        }
    }

    private fun text(
        value: String,
        size: Float = 14f,
        color: Int = white,
        bold: Boolean = false
    ): TextView {
        return TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(null, Typeface.BOLD)
        }
    }

    private fun column(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
    }

    private fun row(): LinearLayout {
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
    }

    private fun cardView(): LinearLayout {
        return column().apply {
            background = rounded(card)
            setPadding(dp(16), dp(15), dp(16), dp(15))
        }
    }

    private fun addSpace(parent: LinearLayout, height: Int = 12) {
        parent.addView(
            View(this),
            LinearLayout.LayoutParams(1, dp(height))
        )
    }

    private fun addLabel(
        parent: LinearLayout,
        label: String,
        value: String,
        valueColor: Int = white
    ) {
        val line = row()

        line.addView(
            text(label, 12f, muted),
            LinearLayout.LayoutParams(0, -2, 1f)
        )

        line.addView(text(value, 13f, valueColor, true))

        parent.addView(line)
        addSpace(parent, 10)
    }

    private fun addCard(
        parent: LinearLayout,
        title: String,
        subtitle: String? = null
    ): LinearLayout {
        val box = cardView()
        box.addView(text(title, 15f, white, true))

        if (subtitle != null) {
            addSpace(box, 5)
            box.addView(text(subtitle, 12f, muted))
        }

        addSpace(parent, 12)
        parent.addView(box)

        return box
    }

    private fun pageContainer(): LinearLayout {
        val outer = column()
        outer.setPadding(dp(16), dp(16), dp(16), dp(20))

        val scroll = ScrollView(this)
        scroll.isFillViewport = true
        scroll.addView(outer)

        content.removeAllViews()
        content.addView(scroll)

        return outer
    }

    private fun showPage(page: String) {
        currentPage = page

        navItems.forEachIndexed { index, item ->
            item.setTextColor(
                if (
                    (page == "Dashboard" && index == 0) ||
                    (page == "Positions" && index == 1) ||
                    (page == "Settings" && index == 2) ||
                    (page == "Activity" && index == 3) ||
                    (page == "More" && index == 4)
                ) yellow else muted
            )
        }

        when (page) {
            "Dashboard" -> dashboardPage()
            "Positions" -> positionsPage()
            "Settings" -> settingsPage()
            "Activity" -> activityPage()
            "More" -> morePage()
        }
    }

    private fun dashboardPage() {
        val root = pageContainer()

        root.addView(text("Dashboard", 23f, white, true))
        addSpace(root, 4)
        root.addView(
            text("Your trading system at a glance", 12f, muted)
        )

        val connection = addCard(
            root,
            "SYSTEM CONNECTION",
            "Checking server and account status..."
        )

        val connectionStatus = text(
            "● Checking connection",
            14f, yellow, true
        )
        connection.addView(connectionStatus)

        addSpace(root, 16)

        val balanceRow = row()

        val available = cardView()
        available.addView(text("AVAILABLE BALANCE", 10f, muted, true))
        addSpace(available, 12)
        val balanceText = text("-- USDT", 20f, green, true)
        available.addView(balanceText)

        val total = cardView()
        total.addView(text("TOTAL BALANCE", 10f, muted, true))
        addSpace(total, 12)
        val totalText = text("-- USDT", 20f, white, true)
        total.addView(totalText)

        balanceRow.addView(
            available,
            LinearLayout.LayoutParams(0, dp(105), 1f).apply {
                marginEnd = dp(6)
            }
        )

        balanceRow.addView(
            total,
            LinearLayout.LayoutParams(0, dp(105), 1f).apply {
                marginStart = dp(6)
            }
        )

        root.addView(balanceRow)
        addSpace(root, 12)

        val cycleCard = addCard(root, "ACTIVE TRADING CYCLES")
        val cycleCount = text("--", 30f, yellow, true)
        cycleCard.addView(cycleCount)
        cycleCard.addView(
            text("Currently monitored cycles", 11f, muted)
        )

        val positionsCard = addCard(root, "ACTIVE POSITIONS")
        val positionsText = text("Loading positions...", 13f, muted)
        positionsCard.addView(positionsText)

        val quick = addCard(root, "QUICK ACCESS")

        addActionButton(quick, "View Positions") {
            showPage("Positions")
        }

        addActionButton(quick, "Coin Settings") {
            showPage("Settings")
        }

        addActionButton(quick, "Notifications & Events") {
            showPage("Activity")
        }

        val refresh = addButton(root, "REFRESH DASHBOARD", yellow)
        refresh.setOnClickListener {
            dashboardPage()
        }

        getJson("$baseUrl/balance") { json, error ->
            if (error != null || json == null) {
                connectionStatus.text =
                    "● Server connection unavailable"
                connectionStatus.setTextColor(red)
                topStatus.text = "● OFFLINE"
                topStatus.setTextColor(red)
            } else {
                val testnet = json.optBoolean("testnet", true)

                connectionStatus.text =
                    if (testnet) "● Connected to Binance Testnet"
                    else "● Live mode detected"

                connectionStatus.setTextColor(
                    if (testnet) green else red
                )

                topStatus.text =
                    if (testnet) "● TESTNET" else "● LIVE"

                topStatus.setTextColor(
                    if (testnet) green else red
                )

                balanceText.text = String.format(
                    "%.4f USDT",
                    json.optDouble("balance", 0.0)
                )

                totalText.text = String.format(
                    "%.4f USDT",
                    json.optDouble("total_balance", 0.0)
                )
            }
        }

        getJson("$baseUrl/cycles/active") { json, _ ->
            if (json != null) {
                val count = json.optInt("active_cycles_count", 0)
                cycleCount.text = count.toString()

                val cycles =
                    json.optJSONArray("cycles") ?: JSONArray()

                positionsText.text =
                    if (cycles.length() == 0) {
                        "No active trading cycles."
                    } else {
                        buildString {
                            for (i in 0 until cycles.length()) {
                                val c = cycles.getJSONObject(i)

                                append(
                                    "${c.optString("symbol")}  •  " +
                                    "${c.optString("direction")}  •  " +
                                    "${c.optString("status")}\n"
                                )
                            }
                        }.trim()
                    }
            } else {
                positionsText.text =
                    "Unable to load active positions."
            }
        }
    }

    private fun positionsPage() {
        val root = pageContainer()

        root.addView(text("Positions", 23f, white, true))
        root.addView(
            text("Active Long and Short trading cycles", 12f, muted)
        )

        val list = addCard(root, "ACTIVE CYCLES")
        list.addView(text("Loading active cycles...", 13f, muted))

        getJson("$baseUrl/cycles/active") { json, _ ->
            list.removeAllViews()
            list.addView(text("ACTIVE CYCLES", 15f, white, true))

            val cycles = json?.optJSONArray("cycles") ?: JSONArray()

            if (cycles.length() == 0) {
                addSpace(list, 12)
                list.addView(
                    text("No active cycles found.", 13f, muted)
                )
            }

            for (i in 0 until cycles.length()) {
                val cycle = cycles.getJSONObject(i)
                val id = cycle.optInt("id")

                addSpace(list, 12)

                list.addView(
                    text(
                        "${cycle.optString("symbol")}  |  " +
                        cycle.optString("direction"),
                        15f, yellow, true
                    )
                )

                addLabel(
                    list,
                    "Status",
                    cycle.optString("status")
                )

                addLabel(
                    list,
                    "Average Entry",
                    cycle.optDouble("average_entry_price").toString()
                )

                addLabel(
                    list,
                    "Filled Quantity",
                    cycle.optDouble("total_filled_quantity").toString()
                )

                val details = addButton(
                    list,
                    "VIEW CYCLE DETAILS",
                    0xFF263B56.toInt()
                )

                details.setOnClickListener {
                    cycleDetails(id)
                }
            }
        }

        addSpace(root, 10)

        root.addView(
            text(
                "Only cycles returned by the server are displayed.",
                11f, muted
            )
        )
    }

    private fun cycleDetails(id: Int) {
        getJson("$baseUrl/cycles/$id") { json, error ->
            if (error != null || json == null) {
                Toast.makeText(
                    this,
                    "Unable to load cycle details",
                    Toast.LENGTH_LONG
                ).show()
                return@getJson
            }

            val message = buildString {
                append("Cycle #$id\n")
                append("${json.optString("symbol")} ")
                append("${json.optString("direction")}\n")
                append("Status: ${json.optString("status")}\n")
                append(
                    "Average: ${json.optDouble("average_entry_price")}\n"
                )
                append(
                    "Quantity: ${json.optDouble("total_filled_quantity")}\n"
                )
                append(
                    "Take Profit: ${json.optDouble("take_profit_price")}\n"
                )
                append(
                    "Re-entry: ${json.optDouble("reentry_price")}\n\n"
                )

                val entries =
                    json.optJSONArray("entries") ?: JSONArray()

                append("ENTRIES\n")

                for (i in 0 until entries.length()) {
                    val e = entries.getJSONObject(i)

                    append(
                        "${e.optString("type")} | " +
                        "${e.optString("status")} | " +
                        "Qty: ${e.optDouble("filled_quantity")}\n"
                    )
                }
            }

            android.app.AlertDialog.Builder(this)
                .setTitle("Cycle Details")
                .setMessage(message)
                .setPositiveButton("CLOSE", null)
                .show()
        }
    }

    private fun settingsPage() {
        val root = pageContainer()

        root.addView(text("Coin Settings", 23f, white, true))
        root.addView(
            text(
                "View saved settings for each trading pair",
                12f, muted
            )
        )

        val box = addCard(root, "SELECT TRADING PAIR")

        val spinner = Spinner(this)
        spinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            symbols
        )

        box.addView(spinner)

        val details = addCard(root, "SAVED CONFIGURATION")
        details.addView(
            text("Select a coin to load its settings.", 13f, muted)
        )

        fun loadSettings(symbol: String) {
            details.removeAllViews()

            details.addView(
                text("$symbol SETTINGS", 15f, yellow, true)
            )

            details.addView(text("Loading...", 13f, muted))

            getJson("$baseUrl/settings/$symbol") { json, error ->
                details.removeAllViews()

                details.addView(
                    text("$symbol SETTINGS", 15f, yellow, true)
                )

                if (error != null || json == null) {
                    details.addView(
                        text(
                            "Settings could not be loaded.",
                            13f, red
                        )
                    )
                    return@getJson
                }

                addLabel(
                    details,
                    "LONG",
                    if (json.optBoolean("enabled_long", true))
                        "ENABLED" else "DISABLED",
                    green
                )

                addLabel(
                    details,
                    "SHORT",
                    if (json.optBoolean("enabled_short", true))
                        "ENABLED" else "DISABLED",
                    green
                )

                addLabel(
                    details,
                    "Initial Margin",
                    "${json.optDouble("initial_margin")} USDT"
                )

                addLabel(
                    details,
                    "Averaging Margin",
                    "${json.optDouble("averaging_margin")} USDT"
                )

                addLabel(
                    details,
                    "Opposite Margin",
                    "${json.optDouble("opposite_margin")} USDT"
                )

                addLabel(
                    details,
                    "Leverage",
                    "${json.optInt("leverage")}x"
                )

                addLabel(
                    details,
                    "Take Profit",
                    "${json.optDouble("tp_percent")}%"
                )

                addLabel(
                    details,
                    "Stop Loss",
                    "${json.optDouble("sl_percent")}%"
                )

                addLabel(
                    details,
                    "Warning",
                    "${json.optDouble("warning_percent")}%"
                )

                addLabel(
                    details,
                    "Opposite Entry",
                    "${json.optDouble("opposite_percent")}%"
                )

                addLabel(
                    details,
                    "Averaging",
                    "${json.optDouble("averaging_percent")}%"
                )

                addLabel(
                    details,
                    "Re-entry",
                    "${json.optDouble("reentry_percent")}%"
                )

                details.addView(
                    text(
                        "Settings are currently view-only in the app.",
                        11f, yellow
                    )
                )
            }
        }

        spinner.onItemSelectedListener =
            object : AdapterView.OnItemSelectedListener {

                override fun onItemSelected(
                    parent: AdapterView<*>?,
                    view: View?,
                    position: Int,
                    id: Long
                ) {
                    selectedSymbol = symbols[position]
                    loadSettings(selectedSymbol)
                }

                override fun onNothingSelected(
                    parent: AdapterView<*>?
                ) {}
            }
    }

    private fun activityPage() {
        val root = pageContainer()

        root.addView(text("Activity Center", 23f, white, true))

        root.addView(
            text(
                "Notifications, bot events and re-entry status",
                12f, muted
            )
        )

        val notifications = addCard(root, "NOTIFICATIONS")
        notifications.addView(
            text("Loading notifications...", 13f, muted)
        )

        val events = addCard(root, "BOT EVENTS")
        events.addView(text("Loading events...", 13f, muted))

        val reentries = addCard(root, "RE-ENTRY RECORDS")
        reentries.addView(text("Loading re-entries...", 13f, muted))

        loadList(
            "$baseUrl/notifications",
            notifications,
            "notifications"
        )

        loadList(
            "$baseUrl/events",
            events,
            "events"
        )

        loadList(
            "$baseUrl/reentries",
            reentries,
            "reentries"
        )
    }

    private fun loadList(
        url: String,
        box: LinearLayout,
        arrayName: String
    ) {
        getJson(url) { json, error ->
            box.removeAllViews()

            box.addView(
                text(arrayName.uppercase(), 15f, white, true)
            )

            if (error != null || json == null) {
                box.addView(text("Unable to load data.", 13f, red))
                return@getJson
            }

            val array =
                json.optJSONArray(arrayName) ?: JSONArray()

            if (array.length() == 0) {
                addSpace(box, 10)
                box.addView(
                    text("No records available.", 13f, muted)
                )
                return@getJson
            }

            for (i in 0 until array.length()) {
                val item = array.getJSONObject(i)

                addSpace(box, 12)

                val title = item.optString(
                    "title",
                    item.optString(
                        "symbol",
                        item.optString("type", "Record")
                    )
                )

                box.addView(text(title, 14f, yellow, true))

                val message = item.optString(
                    "message",
                    item.optString(
                        "status",
                        item.optString("severity", "")
                    )
                )

                if (message.isNotBlank()) {
                    box.addView(text(message, 12f, white))
                }

                val date = item.optString("created_at", "")

                if (date.isNotBlank()) {
                    box.addView(text(date, 10f, muted))
                }
            }
        }
    }

    private fun morePage() {
        val root = pageContainer()

        root.addView(text("More", 23f, white, true))

        root.addView(
            text(
                "System information and additional sections",
                12f, muted
            )
        )

        // MANUAL ENTRY
        val manual = addCard(
            root,
            "MANUAL TRADING",
            "Prepare your initial entry configuration"
        )

        addActionButton(manual, "OPEN MANUAL ENTRY") {
            val intent = Intent(
                this,
                ManualEntryActivity::class.java
            )
            startActivity(intent)
        }

        val system = addCard(root, "SYSTEM INFORMATION")

        addLabel(
            system,
            "Application",
            "Binance Futures Bot"
        )

        addLabel(
            system,
            "Version",
            "1.0"
        )

        addLabel(
            system,
            "Trading Environment",
            "Testnet only",
            green
        )

        addLabel(
            system,
            "Live Trading",
            "Disabled",
            red
        )

        val orders = addCard(root, "ORDER MANAGEMENT")

        orders.addView(
            text(
                "Order history screen is reserved. " +
                "A read-only order history API is required before real order records can be displayed.",
                12f, muted
            )
        )

        val history = addCard(root, "TRADE HISTORY")

        history.addView(
            text(
                "Closed cycle history will appear here after a dedicated history API is added.",
                12f, muted
            )
        )

        val safety = addCard(root, "TRADING SAFETY")

        safety.addView(
            text(
                "Manual entry and all trading actions remain disabled. " +
                "This app screen does not submit orders.",
                12f, yellow
            )
        )
    }

    private fun addButton(
        parent: LinearLayout,
        label: String,
        color: Int
    ): Button {
        val button = Button(this)

        button.text = label
        button.textSize = 12f

        button.setTextColor(
            if (color == yellow) Color.BLACK else white
        )

        button.background = rounded(color, 12)
        button.isAllCaps = false

        parent.addView(
            button,
            LinearLayout.LayoutParams(
                -1,
                dp(48)
            ).apply {
                topMargin = dp(8)
            }
        )

        return button
    }

    private fun addActionButton(
        parent: LinearLayout,
        label: String,
        action: () -> Unit
    ) {
        val button = addButton(
            parent,
            label,
            0xFF263B56.toInt()
        )

        button.setOnClickListener {
            action()
        }
    }

    private fun getJson(
        url: String,
        callback: (JSONObject?, String?) -> Unit
    ) {
        val request = Request.Builder()
            .url(url)
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {

            override fun onFailure(
                call: Call,
                e: IOException
            ) {
                runOnUiThread {
                    callback(
                        null,
                        e.message ?: "Network error"
                    )
                }
            }

            override fun onResponse(
                call: Call,
                response: Response
            ) {
                val body = response.body?.string()

                runOnUiThread {
                    if (!response.isSuccessful || body == null) {
                        callback(
                            null,
                            "HTTP ${response.code}"
                        )
                    } else {
                        try {
                            callback(
                                JSONObject(body),
                                null
                            )
                        } catch (e: Exception) {
                            callback(
                                null,
                                "Invalid server response"
                            )
                        }
                    }
                }
            }
        })
    }

    override fun onDestroy() {
        super.onDestroy()
        client.dispatcher.cancelAll()
    }
}
