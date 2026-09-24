package com.baatx.domain.model

import java.time.Instant

data class Customer(
    val id: String,
    val name: String?,
    val phoneMasked: String?,
    val requirement: String?,
    val location: String?,
    val budgetLabel: String?,
    val leadStatus: LeadStatus,
    val leadScore: Int,
    val purchaseIntent: String,
    val summary: String?,
    val nextFollowUpAt: Instant?,
    val lastInteractionAt: Instant?,
)

enum class LeadStatus(val apiValue: String, val label: String) {
    NEW("new", "New"),
    CONTACTED("contacted", "Contacted"),
    INTERESTED("interested", "Interested"),
    FOLLOW_UP("follow_up", "Follow-up"),
    HOT("hot", "Hot"),
    CONVERTED("converted", "Converted"),
    LOST("lost", "Lost");

    companion object {
        fun from(value: String?): LeadStatus = entries.firstOrNull { it.apiValue == value } ?: NEW
    }
}

enum class FollowUpType(val apiValue: String, val label: String) {
    CALL_CUSTOMER("call_customer", "Call customer"),
    WHATSAPP_CUSTOMER("whatsapp_customer", "WhatsApp customer"),
    SEND_QUOTATION("send_quotation", "Send quotation"),
    SEND_EMAIL("send_email", "Send email"),
    MEET_CUSTOMER("meet_customer", "Meet customer"),
    CHECK_AVAILABILITY("check_availability", "Check availability"),
    DISCUSS_PRICE("discuss_price", "Discuss price"),
    SCHEDULE_TEST_DRIVE("schedule_test_drive", "Schedule test drive"),
    SHOW_PROPERTY("show_property", "Show property"),
    SEND_DOCUMENT("send_document", "Send document"),
    PAYMENT_FOLLOW_UP("payment_follow_up", "Payment follow-up"),
    GENERAL_FOLLOW_UP("general_follow_up", "General follow-up"),
    OTHER("other", "Other");

    companion object {
        fun from(value: String?): FollowUpType =
            entries.firstOrNull { it.apiValue == value } ?: GENERAL_FOLLOW_UP
    }
}

data class FollowUp(
    val id: String,
    val customerId: String,
    val customerName: String?,
    val phoneMasked: String?,
    val type: FollowUpType,
    val title: String,
    val reason: String?,
    val dueAt: Instant,
    val isOverdue: Boolean,
    val createdByAi: Boolean,
    val customerRequestedCallback: Boolean,
    val status: String,
)

data class FollowUpBoard(
    val today: List<FollowUp> = emptyList(),
    val tomorrow: List<FollowUp> = emptyList(),
    val upcoming: List<FollowUp> = emptyList(),
    val overdue: List<FollowUp> = emptyList(),
    val completed: List<FollowUp> = emptyList(),
)

/** One row on the "Here's what I understood" screen. */
data class ReviewItem(
    val key: String,
    val label: String,
    val value: String,
    val confidence: Double,
    val band: ConfidenceBand,
    val needsConfirmation: Boolean,
    val sourceText: String?,
)

enum class ConfidenceBand {
    HIGH, MEDIUM, LOW;

    companion object {
        fun from(value: String?): ConfidenceBand = when (value) {
            "high" -> HIGH
            "medium" -> MEDIUM
            else -> LOW
        }
    }
}

data class DetectedFollowUp(
    val required: Boolean,
    val rawDate: String?,
    val type: FollowUpType,
    val action: String?,
    val reason: String?,
    val resolvedDueAt: Instant?,
    val needsConfirmation: Boolean,
    val customerRequestedCallback: Boolean,
)

data class ExtractionReview(
    val extractionId: String,
    val jobId: String,
    val customerId: String?,
    val matchedExistingCustomer: Boolean,
    val title: String,
    val items: List<ReviewItem>,
    val summary: String?,
    val followUp: DetectedFollowUp,
    val overallConfidence: Double,
)

data class ProcessingJob(
    val id: String,
    val status: String,
    val stageLabel: String,
    val progress: Int,
    val extractionId: String?,
    val errorMessage: String?,
) {
    val isReadyForReview: Boolean get() = status == "awaiting_review"
    val isFailed: Boolean get() = status == "failed"
    val isTerminal: Boolean
        get() = status in setOf("awaiting_review", "applied", "failed", "cancelled")
}

data class DashboardSnapshot(
    val greeting: String,
    val prompt: String,
    val followUpsToday: Int,
    val newLeads: Int,
    val hotLeads: Int,
    val overdue: Int,
    val newCustomers: Int,
    val convertedToday: Int,
    val aiActivity: List<AIActivity>,
)

data class AIActivity(
    val customerId: String?,
    val customerName: String?,
    val action: String,
    val at: Instant?,
)
