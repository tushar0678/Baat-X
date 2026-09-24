package com.baatx.data.remote

import com.baatx.data.remote.dto.*
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.*

interface AuthApi {
    @Headers("No-Auth: true")
    @POST("api/v1/auth/signup")
    suspend fun signup(@Body body: SignupRequest): TokenResponse

    @Headers("No-Auth: true")
    @POST("api/v1/auth/login")
    suspend fun login(@Body body: LoginRequest): TokenResponse

    @Headers("No-Auth: true")
    @POST("api/v1/auth/refresh")
    suspend fun refresh(@Body body: RefreshRequest): TokenResponse

    @GET("api/v1/auth/me")
    suspend fun me(): UserProfileDto
}

interface AiApi {
    @POST("api/v1/ai/tell-ai")
    suspend fun tellAi(@Body body: TellAIRequest): JobResponse

    /**
     * `phone_hint`/`name_hint` carry the contact of the call this recording
     * belongs to. The phone number is what links the conversation to an
     * existing customer, so a repeat call lands on the same CRM record.
     */
    @Multipart
    @POST("api/v1/ai/process-audio")
    suspend fun processAudio(
        @Part file: MultipartBody.Part,
        @Part("idempotency_key") idempotencyKey: RequestBody,
        @Part("source") source: RequestBody,
        @Part("customer_id") customerId: RequestBody? = null,
        @Part("phone_hint") phoneHint: RequestBody? = null,
        @Part("name_hint") nameHint: RequestBody? = null,
    ): JobResponse

    @GET("api/v1/ai/jobs/{jobId}")
    suspend fun jobStatus(@Path("jobId") jobId: String): JobResponse

    @GET("api/v1/ai/jobs/{jobId}/review")
    suspend fun review(@Path("jobId") jobId: String): ExtractionReviewDto

    @POST("api/v1/ai/jobs/{jobId}/reanalyze")
    suspend fun reanalyze(@Path("jobId") jobId: String): JobResponse

    @POST("api/v1/ai/extractions/{extractionId}/apply")
    suspend fun apply(
        @Path("extractionId") extractionId: String,
        @Body body: ApplyExtractionRequest,
    ): ApplyExtractionResponse
}

interface CrmApi {
    @GET("api/v1/customers")
    suspend fun customers(
        @Query("search") search: String? = null,
        @Query("lead_status") leadStatus: String? = null,
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 20,
        @Query("sort_by") sortBy: String = "updated_at",
        @Query("sort_dir") sortDir: String = "desc",
    ): PageDto<CustomerDto>

    @GET("api/v1/customers/{id}")
    suspend fun customer(@Path("id") id: String): CustomerDto

    @PATCH("api/v1/customers/{id}")
    suspend fun updateCustomer(
        @Path("id") id: String,
        @Body body: Map<String, String?>,
    ): CustomerDto

    @GET("api/v1/customers/{id}/timeline")
    suspend fun timeline(@Path("id") id: String): CustomerTimelineDto

    @GET("api/v1/leads")
    suspend fun leads(
        @Query("status") status: String? = null,
        @Query("page") page: Int = 1,
    ): PageDto<LeadDto>

    @GET("api/v1/leads/funnel")
    suspend fun funnel(): LeadFunnelDto

    @PATCH("api/v1/leads/{id}/status")
    suspend fun updateLeadStatus(
        @Path("id") id: String,
        @Body body: Map<String, String>,
    ): LeadDto

    @POST("api/v1/leads/{id}/convert")
    suspend fun convert(@Path("id") id: String, @Body body: Map<String, String>): LeadDto
}

interface FollowUpApi {
    @GET("api/v1/follow-ups")
    suspend fun board(@Query("mine_only") mineOnly: Boolean = false): FollowUpBoardDto

    @POST("api/v1/follow-ups")
    suspend fun create(@Body body: FollowUpCreateRequest): FollowUpDto

    @PATCH("api/v1/follow-ups/{id}")
    suspend fun update(@Path("id") id: String, @Body body: FollowUpUpdateRequest): FollowUpDto

    @GET("api/v1/notifications")
    suspend fun notifications(): List<NotificationDto>
}

interface ReportApi {
    @GET("api/v1/dashboard")
    suspend fun dashboard(): DashboardDto

    @GET("api/v1/reports/daily")
    suspend fun daily(@Query("date") date: String? = null): DailyReportDto

    @GET("api/v1/reports/weekly")
    suspend fun weekly(): PeriodReportDto

    @GET("api/v1/reports/monthly")
    suspend fun monthly(): PeriodReportDto
}

interface AssistantApi {
    @POST("api/v1/assistant/query")
    suspend fun query(@Body body: AssistantQueryRequest): AssistantResponseDto
}

interface WhatsAppApi {
    @POST("api/v1/whatsapp/draft")
    suspend fun draft(@Body body: WhatsAppDraftRequest): WhatsAppDraftDto

    /** Sending always requires `approved = true`; the server enforces it too. */
    @POST("api/v1/whatsapp/send")
    suspend fun send(@Body body: WhatsAppSendRequest): Map<String, String?>
}
