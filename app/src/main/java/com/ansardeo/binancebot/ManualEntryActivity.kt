package com.ansardeo.binancebot

import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.EditText
import android.widget.RadioGroup
import android.widget.Spinner
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class ManualEntryActivity : AppCompatActivity() {

    private val symbols = arrayOf(
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT"
    )

    private val leverages = arrayOf(
        "1x", "2x", "3x", "5x", "10x"
    )

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_manual_entry)

        val symbolSpinner = findViewById<Spinner>(R.id.spEntrySymbol)
        val leverageSpinner = findViewById<Spinner>(R.id.spEntryLeverage)
        val directionGroup = findViewById<RadioGroup>(R.id.rgDirection)
        val marginInput = findViewById<EditText>(R.id.etEntryMargin)
        val summary = findViewById<TextView>(R.id.txtEntrySummary)

        symbolSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            symbols
        )

        leverageSpinner.adapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            leverages
        )

        leverageSpinner.setSelection(3)

        val updateSummary = {
            val symbol = symbolSpinner.selectedItem?.toString() ?: "BTCUSDT"
            val direction = if (directionGroup.checkedRadioButtonId == R.id.rbShort) "SHORT" else "LONG"
            val margin = marginInput.text.toString().ifBlank { "0" }
            val leverage = leverageSpinner.selectedItem?.toString() ?: "5x"

            summary.text = "Pair: $symbol\n" +
                    "Direction: $direction\n" +
                    "Margin: $margin USDT\n" +
                    "Leverage: $leverage\n\n" +
                    "Status: Preview only"
        }

        symbolSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                updateSummary()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        leverageSpinner.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>?, view: View?, position: Int, id: Long) {
                updateSummary()
            }
            override fun onNothingSelected(parent: AdapterView<*>?) {}
        }

        directionGroup.setOnCheckedChangeListener { _, _ ->
            updateSummary()
        }

        marginInput.addTextChangedListener(object : TextWatcher {
            override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}
            override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                updateSummary()
            }
            override fun afterTextChanged(s: Editable?) {}
        })

        updateSummary()
    }
}
