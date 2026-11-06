package com.ansardeo.binancebot

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException

class MainActivity : AppCompatActivity() {

    private lateinit var txtStatus: TextView
    private lateinit var txtBalance: TextView
    private lateinit var etSymbol: EditText
    private lateinit var etDirection: EditText
    private lateinit var etMargin: EditText
    private lateinit var btnSubmitEntry: Button
    private lateinit var btnRefresh: Button

    private val client = OkHttpClient()
    private val backendBaseUrl = "https://ansardeo-sco-binance-android-bot.hf.space/api/v1"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        txtStatus = findViewById(R.id.txtStatus)
        txtBalance = findViewById(R.id.txtBalance)
        etSymbol = findViewById(R.id.etSymbol)
        etDirection = findViewById(R.id.etDirection)
        etMargin = findViewById(R.id.etMargin)
        btnSubmitEntry = findViewById(R.id.btnSubmitEntry)
        btnRefresh = findViewById(R.id.btnRefresh)

        txtStatus.text = "Status: Connected & Monitoring"

        // Fetch balance on startup
        fetchAccountBalance()

        btnSubmitEntry.setOnClickListener {
            val symbol = etSymbol.text.toString().trim().uppercase()
            val direction = etDirection.text.toString().trim().uppercase()
            val marginStr = etMargin.text.toString().trim()

            if (symbol.isEmpty() || direction.isEmpty() || marginStr.isEmpty()) {
                Toast.makeText(this, "Please fill in all fields", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val margin = marginStr.toDoubleOrNull() ?: 10.0
            sendInitialEntryToServer(symbol, direction, margin)
        }

        btnRefresh.setOnClickListener {
            fetchAccountBalance()
        }
    }

    private fun fetchAccountBalance() {
        txtBalance.text = "Fetching..."
        val request = Request.Builder()
            .url("$backendBaseUrl/balance")
            .get()
            .build()

        client.newCall(request).enqueue(object : Callback {
            private fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    txtBalance.text = "Error Loading"
                    Toast.makeText(this@MainActivity, "Failed to fetch balance", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    txtBalance.text = "Connection Failed"
                }
            }

            override fun onResponse(call: Call, response: Response) {
                val responseData = response.body?.string()
                runOnUiThread {
                    if (response.isSuccessful && responseData != null) {
                        try {
                            val json = JSONObject(responseData)
                            val balance = json.optDouble("balance", 0.0)
                            txtBalance.text = "$$balance USDT"
                        } catch (e: Exception) {
                            txtBalance.text = "Parse Error"
                        }
                    } else {
                        txtBalance.text = "Unavailable"
                    }
                }
            }
        })
    }

    private fun sendInitialEntryToServer(symbol: String, direction: String, margin: Double) {
        val jsonBody = JSONObject().apply {
            put("symbol", symbol)
            put("direction", direction)
            put("initial_margin", margin)
            put("leverage", 10)
        }

        val body = jsonBody.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
        val request = Request.Builder()
            .url("$backendBaseUrl/trade/initial-entry")
            .post(body)
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) {
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "Connection Failed: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }

            override fun onResponse(call: Call, response: Response) {
                runOnUiThread {
                    if (response.isSuccessful) {
                        Toast.makeText(this@MainActivity, "Trading Cycle Started Successfully!", Toast.LENGTH_LONG).show()
                        fetchAccountBalance() // Refresh balance after starting trade
                    } else {
                        Toast.makeText(this@MainActivity, "Server Error: ${response.code}", Toast.LENGTH_LONG).show()
                    }
                }
            }
        })
    }
}
