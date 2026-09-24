package com.baatx

import com.baatx.data.repository.formatIndianMoney
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MoneyFormatTest {

    @Test
    fun `lakh amounts use Indian phrasing`() {
        assertEquals("₹70 lakh", formatIndianMoney(7_000_000.0))
        assertEquals("₹1.50 lakh", formatIndianMoney(150_000.0))
    }

    @Test
    fun `crore amounts use Indian phrasing`() {
        assertEquals("₹1.20 crore", formatIndianMoney(12_000_000.0))
    }

    @Test
    fun `missing or zero budget renders nothing`() {
        assertNull(formatIndianMoney(null))
        assertNull(formatIndianMoney(0.0))
    }
}
