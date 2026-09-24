package com.baatx.data.repository

import com.baatx.data.remote.dto.*
import com.baatx.domain.model.*
import java.time.Instant
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

internal fun String?.toInstantOrNull(): Instant? =
    this?.let { runCatching { Instant.parse(it) }.getOrNull() }

/** ₹70,00,000 -> "₹70 lakh" - the way Indian sellers actually talk about money. */
fun formatIndianMoney(amount: Double?, currency: String = "INR"): String? {
    if (amount == null || amount <= 0) return null
    val symbol = if (currency == "INR") "₹" else "$currency "
    return when {
        amount >= 10_000_000 -> "$symbol${trim(amount / 10_000_000)} crore"
        amount >= 100_000 -> "$symbol${trim(amount / 100_000)} lakh"
        amount >= 1_000 -> "$symbol${trim(amount / 1_000)}K"
        else -> "$symbol${trim(amount)}"
    }
}

private fun trim(value: Double): String =
    if (value % 1.0 == 0.0) value.toLong().toString() else String.format("%.2f", value)

fun CustomerDto.toDomain(): Customer = Customer(
    id = id,
    name = name,
    phoneMasked = phoneMasked,
    requirement = requirement ?: product,
    location = location,
    budgetLabel = formatIndianMoney(budgetMax ?: budgetMin, currency),
    leadStatus = LeadStatus.from(leadStatus),
    leadScore = leadScore,
    purchaseIntent = purchaseIntent,
    summary = summary,
    nextFollowUpAt = nextFollowUpAt.toInstantOrNull(),
    lastInteractionAt = lastInteractionAt.toInstantOrNull(),
)

fun FollowUpDto.toDomain(): FollowUp = FollowUp(
    id = id,
    customerId = customerId,
    customerName = customerName,
    phoneMasked = customerPhoneMasked,
    type = FollowUpType.from(type),
    title = title,
    reason = reason,
    dueAt = dueAt.toInstantOrNull() ?: Instant.now(),
    isOverdue = isOverdue,
    createdByAi = createdByAi,
    customerRequestedCallback = customerRequestedCallback,
    status = status,
)

fun FollowUpBoardDto.toDomain(): FollowUpBoard = FollowUpBoard(
    today = today.map { it.toDomain() },
    tomorrow = tomorrow.map { it.toDomain() },
    upcoming = upcoming.map { it.toDomain() },
    overdue = overdue.map { it.toDomain() },
    completed = completed.map { it.toDomain() },
)

private fun JsonElement.render(): String = when (this) {
    is JsonPrimitive -> content
    is JsonArray -> joinToString(", ") { it.render() }
    else -> toString()
}

fun ExtractionReviewDto.toDomain(): ExtractionReview = ExtractionReview(
    extractionId = extractionId,
    jobId = jobId,
    customerId = customerId,
    matchedExistingCustomer = matchedExistingCustomer,
    title = title,
    items = items.mapNotNull { item ->
        val rendered = item.value?.render()?.takeIf { it.isNotBlank() && it != "null" }
            ?: return@mapNotNull null
        ReviewItem(
            key = item.key,
            label = item.label,
            value = rendered,
            confidence = item.confidence,
            band = ConfidenceBand.from(item.band),
            needsConfirmation = item.needsConfirmation,
            sourceText = item.sourceText,
        )
    },
    summary = summary,
    followUp = DetectedFollowUp(
        required = followUp.required,
        rawDate = followUp.date,
        type = FollowUpType.from(followUp.type),
        action = followUp.action,
        reason = followUp.reason,
        resolvedDueAt = followUp.resolvedDueAt.toInstantOrNull(),
        needsConfirmation = followUp.needsConfirmation,
        customerRequestedCallback = followUp.customerRequestedCallback,
    ),
    overallConfidence = overallConfidence,
)

fun JobResponse.toDomain(): ProcessingJob = ProcessingJob(
    id = jobId,
    status = status,
    stageLabel = stageLabel,
    progress = progress,
    extractionId = extractionId,
    errorMessage = errorMessage,
)

fun DashboardDto.toDomain(): DashboardSnapshot = DashboardSnapshot(
    greeting = greeting,
    prompt = prompt,
    followUpsToday = today.followUps,
    newLeads = today.newLeads,
    hotLeads = today.hotLeads,
    overdue = today.overdue,
    newCustomers = conversions.newCustomers,
    convertedToday = conversions.convertedToday,
    aiActivity = aiActivity.map {
        AIActivity(it.customerId, it.customerName, it.action, it.at.toInstantOrNull())
    },
)
