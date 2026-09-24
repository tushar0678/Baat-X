package com.baatx

import com.baatx.core.network.ErrorMapper
import java.net.UnknownHostException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException

class ErrorMapperTest {

    @Test
    fun `offline errors get the friendly network message`() {
        val error = ErrorMapper.map(UnknownHostException("no dns"))
        assertTrue(error.isOffline)
        assertEquals(
            "Internet connection was lost. We'll continue when you're back online.",
            error.message,
        )
    }

    @Test
    fun `server errors never leak status codes to the user`() {
        val error = ErrorMapper.map(httpException(500, """{"code":"x","message":""}"""))
        assertTrue(error.isRetryable)
        assertTrue(!error.message.contains("500"))
    }

    @Test
    fun `unsupported audio surfaces the supported formats`() {
        val body = """{"code":"unsupported_audio","message":""" +
            """"This audio format isn't supported. Please select MP3, M4A, WAV, AAC, AMR, or OGG."}"""
        val error = ErrorMapper.map(httpException(415, body))
        assertTrue(error.message.contains("MP3, M4A, WAV, AAC, AMR, or OGG"))
    }

    private fun httpException(code: Int, body: String): HttpException {
        val response = Response.Builder()
            .code(code)
            .message("error")
            .protocol(Protocol.HTTP_1_1)
            .request(Request.Builder().url("https://api.baatx.test/").build())
            .build()
        return HttpException(
            retrofit2.Response.error<Any>(body.toResponseBody("application/json".toMediaType()), response),
        )
    }
}
