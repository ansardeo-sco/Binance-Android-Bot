package com.ansardeo.binancebot

import android.os.Bundle
import android.view.View
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

    // سرور تبدیل ہونے پر یہاں اصل VPS API address درج کیا جائے گا۔
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

    // اس مرحلے میں ٹریڈنگ جان بوجھ کر بند ہے۔
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
            if (!tradingEnabled) {
                Toast.makeText(
                    this,
                    "Trading will be enabled after Testnet testing.",
                    Toast.LENGTH_LONG
                ).show()
                return@setOnClickListener
            }
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
    }

    private fun refreshDashboard() {

        btnRefresh.isEnabled = false
        btnRefresh.text = "REFRESHING..."

        fetchAccountBalance()
        fetchActiveCycles()
    }

    private fun finishRefreshButton() {
        btnRefresh.isEnabled = true
        btnRefresh.text = "REFRESH DASHBOARD"
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
                                    "SERVER: CONNECTED - LIVE MODE DETECTED"
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
                                    display.append("  |  ")
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
