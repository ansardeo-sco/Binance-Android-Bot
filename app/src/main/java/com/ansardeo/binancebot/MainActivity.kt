package com.ansardeo.binancebot

import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import java.io.IOException
import java.util.concurrent.TimeUnit
import org.json.JSONObject

class MainActivity : AppCompatActivity() {

    private lateinit var txtStatus: TextView
    private lateinit var txtMode: TextView
    private lateinit var txtBalance: TextView
    private lateinit var txtTotalBalance: TextView
    private lateinit var txtCycleCount: TextView
    private lateinit var txtActivePositions: TextView
    private lateinit var txtSymbolSettings: TextView

    private lateinit var spSymbol: Spinner
    private lateinit var spLeverage: Spinner
    private lateinit var rgDirection: RadioGroup
    private lateinit var etMargin: EditText

    private lateinit var btnSubmitEntry: Button
    private lateinit var btnRefresh: Button

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(20, TimeUnit.SECONDS)
        .writeTimeout(20, TimeUnit.SECONDS)
        .build()

    private val backendBaseUrl =
        "https://ansardeo-sco-binance-android-bot.hf.space/api/v1"

    private val symbols = arrayOf(
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT"
    )

    private val leverageOptions = arrayOf(
        "1x",
        "2x",
        "3x",
        "5x",
        "6x",
        "10x",
        "15x",
        "20x"
    )

    // Testnet جانچ مکمل ہونے تک ٹریڈنگ بند رہے گی۔
    private val tradingEnabled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        initializeViews()
        setupSpinners()
        setupDashboard()

        btnRefresh.setOnClickListener {
            refreshDashboard()
        }

        btnSubmitEntry.setOnClickListener {
            Toast.makeText(
                this,
                "Trading is disabled until Testnet testing is completed.",
                Toast.LENGTH_LONG
            ).show()
        }

        refreshDashboard()
    }

    private fun initializeViews() {

        txtStatus = findViewById(R.id.txtStatus)
        txtMode = findViewById(R.id.txtMode)
        txtBalance = findViewById(R.id.txtBalance)
        txtTotalBalance = findViewById(R.id.txtTotalBalance)
        txtCycleCount = findViewById(R.id.txtCycleCount)
        txtActivePositions = findViewById(R.id.txtActivePositions)
        txtSymbolSettings = findViewById(R.id.txtSymbolSettings)

        spSymbol = findViewById(R.id.spSymbol)
        spLeverage = findViewById(R.id.spLeverage)
        rgDirection = findViewById(R.id.rgDirection)
        etMargin = findViewById(R.id.etMargin)

        btnSubmitEntry = findViewById(R.id.btnSubmitEntry)
        btnRefresh = findViewById(R.id.btnRefresh)
    }

    private fun setupSpinners() {

        val symbolAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            symbols
        )

        symbolAdapter.setDropDownViewResource(
            android.R.layout.simple_spinner_dropdown_item
        )

        spSymbol.adapter = symbolAdapter

        val leverageAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_item,
            leverageOptions
        )

        leverageAdapter.setDropDownViewResource(
            android.R.layout.simple_spinner_dropdown_item
        )

        spLeverage.adapter = leverageAdapter
        spLeverage.setSelection(4)

        spSymbol.onItemSelectedListener =
            object : AdapterView.OnItemSelectedListener {

                override fun onItemSelected(
                    parent: AdapterView<*>?,
                    view: View?,
                    position: Int,
                    id: Long
                ) {
                    val symbol = symbols[position]
                    fetchSymbolSettings(symbol)
                }

                override fun onNothingSelected(
                    parent: AdapterView<*>?
                ) {
                    txtSymbolSettings.text =
                        "No coin selected."
                }
            }
    }

    private fun setupDashboard() {

        txtStatus.text = "SERVER: CHECKING CONNECTION"
        txtMode.text = "MODE: TESTNET CONFIGURATION"

        txtBalance.text = "-- USDT"
        txtTotalBalance.text = "-- USDT"
        txtCycleCount.text = "0"

        etMargin.setText("2.0")

        btnSubmitEntry.isEnabled = tradingEnabled
        btnSubmitEntry.text =
            if (tradingEnabled) {
                "START TRADING CYCLE"
            } else {
                "TRADING DISABLED - TESTING PENDING"
            }

        btnSubmitEntry.alpha =
            if (tradingEnabled) 1.0f else 0.55f

        txtActivePositions.text =
            "Loading active cycles..."

        txtSymbolSettings.text =
            "Loading selected coin settings..."
    }

    private fun refreshDashboard() {

        btnRefresh.isEnabled = false
        btnRefresh.text = "REFRESHING..."

        fetchAccountBalance()
        fetchActiveCycles()

        if (spSymbol.selectedItem != null) {
            fetchSymbolSettings(
                spSymbol.selectedItem.toString()
            )
        }
    }

    private fun finishRefreshButton() {
        btnRefresh.isEnabled = true
        btnRefresh.text = "REFRESH DASHBOARD"
    }

    private fun fetchSymbolSettings(symbol: String) {

        txtSymbolSettings.text =
            "Loading $symbol settings..."

        val request = Request.Builder()
            .url("$backendBaseUrl/settings/$symbol")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {

            override fun onFailure(call: Call, e: IOException) {

                runOnUiThread {
                    txtSymbolSettings.text =
                        "Unable to load $symbol settings.\n" +
                        "Check server connection."
                }
            }

            override fun onResponse(
                call: Call,
                response: Response
            ) {

                val responseData = response.body?.string()

                runOnUiThread {

                    if (response.isSuccessful && responseData != null) {

                        try {

                            val json = JSONObject(responseData)

                            val enabledLong =
                                json.optBoolean("enabled_long", true)

                            val enabledShort =
                                json.optBoolean("enabled_short", true)

                            val initialMargin =
                                json.optDouble("initial_margin", 2.0)

                            val averagingMargin =
                                json.optDouble("averaging_margin", 2.0)

                            val oppositeMargin =
                                json.optDouble("opposite_margin", 2.0)

                            val leverage =
                                json.optInt("leverage", 6)

                            val tp =
                                json.optDouble("tp_percent", 3.0)

                            val sl =
                                json.optDouble("sl_percent", 12.0)

                            val warning =
                                json.optDouble("warning_percent", 6.0)

                            val opposite =
                                json.optDouble("opposite_percent", 7.0)

                            val averaging =
                                json.optDouble("averaging_percent", 9.0)

                            val reentry =
                                json.optDouble("reentry_percent", 1.0)

                            // منتخب کوائن کا مارجن اور لیوریج دکھائیں۔
                            etMargin.setText(
                                initialMargin.toString()
                            )

                            val leverageIndex =
                                leverageOptions.indexOf("${leverage}x")

                            if (leverageIndex >= 0) {
                                spLeverage.setSelection(leverageIndex)
                            }

                            val directionText =
                                "LONG: ${if (enabledLong) "ENABLED" else "DISABLED"}\n" +
                                "SHORT: ${if (enabledShort) "ENABLED" else "DISABLED"}"

                            txtSymbolSettings.text =
                                "$symbol SETTINGS\n\n" +
                                "$directionText\n\n" +
                                "Initial Margin: $initialMargin USDT\n" +
                                "Averaging Margin: $averagingMargin USDT\n" +
                                "Opposite Margin: $oppositeMargin USDT\n" +
                                "Leverage: ${leverage}x\n\n" +
                                "Take Profit: $tp%\n" +
                                "Stop Loss: $sl%\n" +
                                "Warning: $warning%\n" +
                                "Opposite Entry: $opposite%\n" +
                                "Averaging: $averaging%\n" +
                                "Re-entry: $reentry%"

                        } catch (e: Exception) {

                            txtSymbolSettings.text =
                                "Invalid settings response."
                        }

                    } else {

                        txtSymbolSettings.text =
                            "Settings unavailable for $symbol."
                    }
                }
            }
        })
    }

    private fun fetchAccountBalance() {

        val request = Request.Builder()
            .url("$backendBaseUrl/balance")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {

            override fun onFailure(call: Call, e: IOException) {

                runOnUiThread {
                    txtStatus.text = "SERVER: CONNECTION FAILED"
                    txtBalance.text = "Unavailable"
                    txtMode.text = "MODE: NOT VERIFIED"
                    finishRefreshButton()
                }
            }

            override fun onResponse(
                call: Call,
                response: Response
            ) {

                val responseData = response.body?.string()

                runOnUiThread {

                    if (response.isSuccessful && responseData != null) {

                        try {

                            val json = JSONObject(responseData)

                            val balance =
                                json.optDouble("balance", 0.0)

                            val totalBalance =
                                json.optDouble("total_balance", 0.0)

                            val testnet =
                                json.optBoolean("testnet", true)

                            txtBalance.text =
                                String.format("%.4f USDT", balance)

                            txtTotalBalance.text =
                                String.format("%.4f USDT", totalBalance)

                            txtMode.text =
                                if (testnet) {
                                    "MODE: BINANCE TESTNET"
                                } else {
                                    "MODE: LIVE - NOT AUTHORIZED"
                                }

                            txtStatus.text =
                                if (testnet) {
                                    "SERVER: CONNECTED"
                                } else {
                                    "SERVER: LIVE MODE DETECTED"
                                }

                        } catch (e: Exception) {

                            txtStatus.text = "SERVER: INVALID RESPONSE"
                            txtBalance.text = "Data Error"
                        }

                    } else {

                        txtStatus.text =
                            "SERVER: CONNECTION UNAVAILABLE"

                        txtBalance.text = "Unavailable"
                    }

                    finishRefreshButton()
                }
            }
        })
    }

    private fun fetchActiveCycles() {

        val request = Request.Builder()
            .url("$backendBaseUrl/cycles/active")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {

            override fun onFailure(call: Call, e: IOException) {

                runOnUiThread {
                    txtCycleCount.text = "--"
                    txtActivePositions.text =
                        "Unable to load active cycles."
                }
            }

            override fun onResponse(
                call: Call,
                response: Response
            ) {

                val responseData = response.body?.string()

                runOnUiThread {

                    if (response.isSuccessful && responseData != null) {

                        try {

                            val json = JSONObject(responseData)

                            val count =
                                json.optInt("active_cycles_count", 0)

                            val cycles =
                                json.optJSONArray("cycles")

                            txtCycleCount.text = count.toString()

                            if (cycles == null || cycles.length() == 0) {

                                txtActivePositions.text =
                                    "No active trading cycles."

                            } else {

                                val display = StringBuilder()

                                for (i in 0 until cycles.length()) {

                                    val cycle =
                                        cycles.getJSONObject(i)

                                    val symbol =
                                        cycle.optString("symbol", "Unknown")

                                    val direction =
                                        cycle.optString("direction", "Unknown")

                                    val status =
                                        cycle.optString("status", "Unknown")

                                    val averagePrice =
                                        cycle.optDouble(
                                            "average_entry_price",
                                            0.0
                                        )

                                    val quantity =
                                        cycle.optDouble(
                                            "total_filled_quantity",
                                            0.0
                                        )

                                    display.append("● ")
                                    display.append(symbol)
                                    display.append(" | ")
                                    display.append(direction)
                                    display.append("\n")

                                    display.append("Status: ")
                                    display.append(status)
                                    display.append("\n")

                                    display.append("Average Entry: ")
                                    display.append(
                                        String.format("%.6f", averagePrice)
                                    )
                                    display.append("\n")

                                    display.append("Quantity: ")
                                    display.append(
                                        String.format("%.6f", quantity)
                                    )

                                    if (i < cycles.length() - 1) {
                                        display.append("\n\n")
                                    }
                                }

                                txtActivePositions.text =
                                    display.toString()
                            }

                        } catch (e: Exception) {

                            txtActivePositions.text =
                                "Unable to read cycle information."
                        }

                    } else {

                        txtActivePositions.text =
                            "Active cycles unavailable."
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
