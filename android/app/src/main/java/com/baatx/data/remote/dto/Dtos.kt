package com.baatx.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class ErrorResponse(
    val code: String,
    val message: String,
    val details: JsonElement? = null,
    @SerialName("request_id") val requestId: String? = null,
)

// ---------------- auth ----------------
@Serializable
data class SignupRequest(
    @SerialName("full_name") val fullName: String,
    val email: String,
    val password: String,
    val phone: String? = null,
    @SerialName("business_name") val businessName: String,
    val vertical: String = "generic",
    val timezone: String = "Asia/Kolkata",
    val currency: String = "INR",
)

@Serializable
data class LoginRequest(val email: String, val password: String)

@Serializable
data class RefreshRequest(@SerialName("refresh_token") val refreshToken: String)

@Serializable
data class BusinessSummaryDto(
    val id: String,
    val name: String,
    val vertical: String,
    val role: String,
    val currency: String = "INR",
    val timezone: String = "Asia/Kolkata",
)

@Serializable
data class UserProfileDto(
    val id: String,
    @SerialName("full_name") val fullName: String,
    val email: String,
    val phone: String? = null,
    val locale: String = "en-IN",
    val businesses: List<BusinessSummaryDto> = emptyList(),
)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("expires_at") val expiresAt: String,
    val user: UserProfileDto,
    @SerialName("active_business_id") val activeBusinessId: String? = null,
)

// ---------------- AI ----------------
@Serializable
data class TellAIRequest(
    val text: String,
    @SerialName("idempotency_key") val idempotencyKey: String,
    @SerialName("customer_id") val customerId: String? = null,
    @SerialName("phone_hint") val phoneHint: String? = null,
    val source: String = "tell_ai",
)

@Serializable
data class JobResponse(
    @SerialName("job_id") val jobId: String,
    val status: String,
    @SerialName("stage_label") val stageLabel: String,
    val progress: Int,
    @SerialName("error_code") val errorCode: String? = null,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("extraction_id") val extractionId: String? = null,
    @SerialName("customer_id") val customerId: String? = null,
)

@Serializable
data class ReviewItemDto(
    val key: String,
    val label: String,
    val value: JsonElement? = null,
    val confidence: Double = 0.0,
    val band: String = "low",
    @SerialName("needs_confirmation") val needsConfirmation: Boolean = false,
    @SerialName("source_text") val sourceText: String? = null,
)

@Serializable
data class FollowUpExtractionDto(
    val required: Boolean = false,
    val date: String? = null,
    val time: String? = null,
    val type: String = "general_follow_up",
    val action: String? = null,
    val reason: String? = null,
    @SerialName("customer_requested_callback") val customerRequestedCallback: Boolean = false,
    val confidence: Double = 0.0,
    @SerialName("resolved_due_at") val resolvedDueAt: String? = null,
    @SerialName("needs_confirmation") val needsConfirmation: Boolean = false,
)

@Serializable
data class ExtractionReviewDto(
    @SerialName("extraction_id") val extractionId: String,
    @SerialName("job_id") val jobId: String,
    @SerialName("customer_id") val customerId: String? = null,
    @SerialName("matched_existing_customer") val matchedExistingCustomer: Boolean = false,
    val title: String = "Here's what I understood",
    val items: List<ReviewItemDto> = emptyList(),
    val summary: String? = null,
    @SerialName("follow_up") val followUp: FollowUpExtractionDto = FollowUpExtractionDto(),
    @SerialName("overall_confidence") val overallConfidence: Double = 0.0,
    @SerialName("needs_confirmation") val needsConfirmation: List<String> = emptyList(),
)

@Serializable
data class ApplyExtractionRequest(
    @SerialName("customer_id") val customerId: String? = null,
    @SerialName("create_customer") val createCustomer: Boolean = true,
    @SerialName("phone_override") val phoneOverride: String? = null,
    @SerialName("edited_fields") val editedFields: Map<String, String> = emptyMap(),
    @SerialName("confirm_follow_up") val confirmFollowUp: Boolean = true,
    @SerialName("follow_up_due_at") val followUpDueAt: String? = null,
    val discard: Boolean = false,
)

@Serializable
data class ApplyExtractionResponse(
    @SerialName("customer_id") val customerId: String,
    @SerialName("follow_up_id") val followUpId: String? = null,
    @SerialName("lead_status") val leadStatus: String = "new",
    @SerialName("updated_fields") val updatedFields: List<String> = emptyList(),
    @SerialName("skipped_low_confidence_fields") val skippedFields: List<String> = emptyList(),
)

// ---------------- CRM ----------------
@Serializable
data class CustomerDto(
    val id: String,
    @SerialName("business_id") val businessId: String? = null,
    val name: String? = null,
    val phone: String? = null,
    @SerialName("normalized_phone") val normalizedPhone: String? = null,
    @SerialName("phone_masked") val phoneMasked: String? = null,
    val email: String? = null,
    val company: String? = null,
    val location: String? = null,
    val requirement: String? = null,
    val product: String? = null,
    val service: String? = null,
    val quantity: String? = null,
    @SerialName("budget_min") val budgetMinRaw: JsonElement? = null,
    @SerialName("budget_max") val budgetMaxRaw: JsonElement? = null,
    val currency: String = "INR",
    val timeline: String? = null,
    val availability: String? = null,
    @SerialName("price_discussion") val priceDiscussion: String? = null,
    @SerialName("purchase_intent") val purchaseIntent: String = "unknown",
    val sentiment: String = "unknown",
    @SerialName("pain_points") val painPoints: List<String>? = null,
    val objections: List<String>? = null,
    val competitors: List<String>? = null,
    @SerialName("decision_maker") val decisionMaker: String? = null,
    val query: String? = null,
    val topic: String? = null,
    val summary: String? = null,
    @SerialName("lead_status") val leadStatus: String = "new",
    @SerialName("lead_score") val leadScore: Int = 0,
    val source: String = "manual",
    @SerialName("owner_user_id") val ownerUserId: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    @SerialName("last_interaction_at") val lastInteractionAt: String? = null,
    @SerialName("next_follow_up_at") val nextFollowUpAt: String? = null,
) {
    /**
     * Pydantic's ``Decimal`` fields can serialize as a JSON number OR a JSON
     * string depending on the active encoder config - reading them as a raw
     * [JsonElement] and converting here means neither case ever fails
     * deserialization; a malformed/unexpected value just becomes `null`
     * instead of crashing the whole customer list.
     */
    val budgetMin: Double?
        get() = budgetMinRaw?.let { runCatching { it.toString().trim('"').toDouble() }.getOrNull() }

    val budgetMax: Double?
        get() = budgetMaxRaw?.let { runCatching { it.toString().trim('"').toDouble() }.getOrNull() }
}​‌

@Serializable
data class PageDto<T>(
    val items: List<T> = emptyList(),
    val page: Int = 1,
    @SerialName("page_size") val pageSize: Int = 20,
    val total: Int = 0,
    @SerialName("has_next") val hasNext: Boolean = false,
)

@Serializable
data class TimelineEntryDto(
    val id: String,
    @SerialName("occurred_at") val occurredAt: String,
    val kind: String,
    val title: String,
    val summary: String? = null,
    val highlights: Map<String, JsonElement>? = null,
)

@Serializable
data class CustomerTimelineDto(
    @SerialName("customer_id") val customerId: String,
    val name: String? = null,
    @SerialName("phone_masked") val phoneMasked: String? = null,
    val entries: List<TimelineEntryDto> = emptyList(),
)

@Serializable
data class LeadDto(
    val id: String,
    @SerialName("customer_id") val customerId: String,
    @SerialName("customer_name") val customerName: String? = null,
    @SerialName("customer_phone_masked") val customerPhoneMasked: String? = null,
    val status: String,
    val score: Int = 0,
    @SerialName("converted_at") val convertedAt: String? = null,
)

@Serializable
data class LeadFunnelDto(
    @SerialName("total_leads") val totalLeads: Int = 0,
    @SerialName("by_status") val byStatus: Map<String, Int> = emptyMap(),
    @SerialName("converted_leads") val convertedLeads: Int = 0,
    @SerialName("conversion_rate") val conversionRate: Double = 0.0,
    @SerialName("converted_today") val convertedToday: Int = 0,
    @SerialName("converted_this_week") val convertedThisWeek: Int = 0,
    @SerialName("converted_this_month") val convertedThisMonth: Int = 0,
)

// ---------------- follow-ups ----------------
@Serializable
data class FollowUpDto(
    val id: String,
    @SerialName("customer_id") val customerId: String,
    @SerialName("customer_name") val customerName: String? = null,
    @SerialName("customer_phone_masked") val customerPhoneMasked: String? = null,
    val type: String = "general_follow_up",
    val status: String = "pending",
    val title: String,
    val reason: String? = null,
    @SerialName("due_at") val dueAt: String,
    @SerialName("created_by_ai") val createdByAi: Boolean = false,
    @SerialName("is_overdue") val isOverdue: Boolean = false,
    @SerialName("customer_requested_callback") val customerRequestedCallback: Boolean = false,
)

@Serializable
data class FollowUpBoardDto(
    val today: List<FollowUpDto> = emptyList(),
    val tomorrow: List<FollowUpDto> = emptyList(),
    val upcoming: List<FollowUpDto> = emptyList(),
    val overdue: List<FollowUpDto> = emptyList(),
    val completed: List<FollowUpDto> = emptyList(),
    val counts: Map<String, Int> = emptyMap(),
)

@Serializable
data class FollowUpCreateRequest(
    @SerialName("customer_id") val customerId: String,
    val type: String = "call_customer",
    val title: String,
    @SerialName("due_at") val dueAt: String,
    val reason: String? = null,
)

@Serializable
data class FollowUpUpdateRequest(
    val status: String? = null,
    @SerialName("due_at") val dueAt: String? = null,
    val notes: String? = null,
)

// ---------------- dashboard & reports ----------------
@Serializable
data class DashboardTodayDto(
    @SerialName("follow_ups") val followUps: Int = 0,
    @SerialName("new_leads") val newLeads: Int = 0,
    @SerialName("hot_leads") val hotLeads: Int = 0,
    val overdue: Int = 0,
)

@Serializable
data class DashboardConversionsDto(
    @SerialName("new_customers") val newCustomers: Int = 0,
    @SerialName("converted_today") val convertedToday: Int = 0,
)

@Serializable
data class AIActivityDto(
    @SerialName("customer_id") val customerId: String? = null,
    @SerialName("customer_name") val customerName: String? = null,
    val action: String,
    val at: String,
)

@Serializable
data class DashboardDto(
    val greeting: String,
    val prompt: String = "What happened with your customer?",
    val today: DashboardTodayDto = DashboardTodayDto(),
    val conversions: DashboardConversionsDto = DashboardConversionsDto(),
    @SerialName("ai_activity") val aiActivity: List<AIActivityDto> = emptyList(),
)

@Serializable
data class FollowUpMetricsDto(
    val created: Int = 0,
    val completed: Int = 0,
    val pending: Int = 0,
    val overdue: Int = 0,
)

@Serializable
data class QueryMetricsDto(
    @SerialName("total_queries") val totalQueries: Int = 0,
    @SerialName("by_category") val byCategory: Map<String, Int> = emptyMap(),
    @SerialName("quotations_requested") val quotationsRequested: Int = 0,
    @SerialName("price_concerns") val priceConcerns: Int = 0,
    @SerialName("callbacks_requested") val callbacksRequested: Int = 0,
    @SerialName("availability_queries") val availabilityQueries: Int = 0,
)

@Serializable
data class ImportantFollowUpDto(
    @SerialName("customer_id") val customerId: String,
    @SerialName("customer_name") val customerName: String? = null,
    val action: String,
    @SerialName("due_at") val dueAt: String,
)

@Serializable
data class DailyReportDto(
    val title: String = "DAILY SALES REPORT",
    @SerialName("report_date") val reportDate: String,
    @SerialName("new_leads") val newLeads: Int = 0,
    @SerialName("customers_contacted") val customersContacted: Int = 0,
    @SerialName("interested_leads") val interestedLeads: Int = 0,
    @SerialName("hot_leads") val hotLeads: Int = 0,
    @SerialName("converted_customers") val convertedCustomers: Int = 0,
    @SerialName("follow_ups") val followUps: FollowUpMetricsDto = FollowUpMetricsDto(),
    val queries: QueryMetricsDto = QueryMetricsDto(),
    @SerialName("important_follow_ups") val importantFollowUps: List<ImportantFollowUpDto> = emptyList(),
    @SerialName("ai_insights") val aiInsights: List<String> = emptyList(),
    @SerialName("insights_are_ai_generated") val insightsAreAiGenerated: Boolean = true,
)

@Serializable
data class LeadMetricsDto(
    @SerialName("new_leads") val newLeads: Int = 0,
    val contacted: Int = 0,
    val interested: Int = 0,
    val hot: Int = 0,
    val converted: Int = 0,
    val lost: Int = 0,
    @SerialName("conversion_rate") val conversionRate: Double = 0.0,
)

@Serializable
data class PeriodReportDto(
    val title: String,
    val period: String,
    @SerialName("period_start") val periodStart: String,
    @SerialName("period_end") val periodEnd: String,
    val leads: LeadMetricsDto = LeadMetricsDto(),
    @SerialName("follow_ups") val followUps: FollowUpMetricsDto = FollowUpMetricsDto(),
    val queries: QueryMetricsDto = QueryMetricsDto(),
    @SerialName("top_requirements") val topRequirements: List<Map<String, JsonElement>> = emptyList(),
    @SerialName("common_objections") val commonObjections: List<Map<String, JsonElement>> = emptyList(),
    @SerialName("important_follow_ups") val importantFollowUps: List<ImportantFollowUpDto> = emptyList(),
    @SerialName("ai_insights") val aiInsights: List<String> = emptyList(),
)

// ---------------- assistant & whatsapp ----------------
@Serializable
data class AssistantQueryRequest(
    val query: String,
    @SerialName("confirm_token") val confirmToken: String? = null,
)

@Serializable
data class AssistantResponseDto(
    val answer: String,
    val kind: String = "answer",
    val data: List<Map<String, JsonElement>> = emptyList(),
    @SerialName("confirm_token") val confirmToken: String? = null,
    @SerialName("is_ai_generated") val isAiGenerated: Boolean = true,
)

@Serializable
data class WhatsAppDraftRequest(
    @SerialName("customer_id") val customerId: String,
    val purpose: String = "follow_up_summary",
)

@Serializable
data class WhatsAppDraftDto(
    @SerialName("message_id") val messageId: String,
    @SerialName("to_phone_masked") val toPhoneMasked: String,
    val body: String,
    val status: String,
    val disclaimer: String = "",
)

@Serializable
data class WhatsAppSendRequest(
    @SerialName("message_id") val messageId: String,
    val approved: Boolean,
    @SerialName("edited_body") val editedBody: String? = null,
)

@Serializable
data class NotificationDto(
    val id: String,
    val type: String,
    val title: String,
    val body: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("read_at") val readAt: String? = null,
)
