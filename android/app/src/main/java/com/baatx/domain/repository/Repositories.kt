package com.baatx.domain.repository

import com.baatx.core.network.ApiResult
import com.baatx.data.remote.dto.*
import com.baatx.domain.model.*
import kotlinx.coroutines.flow.Flow

interface AuthRepository {
    val isSignedIn: Flow<Boolean>
    suspend fun login(email: String, password: String): ApiResult<UserProfileDto>
    suspend fun signup(
        fullName: String,
        email: String,
        password: String,
        businessName: String,
        vertical: String,
    ): ApiResult<UserProfileDto>
    fun signOut()
    fun currentUserName(): String?
}

interface ConversationRepository {
    /** Queues a Tell AI note; works offline and syncs later. */
    suspend fun tellAi(
        text: String,
        customerId: String? = null,
        phoneHint: String? = null,
    ): ApiResult<ProcessingJob?>

    /**
     * Uploads a recording the user picked.
     *
     * `phoneHint`/`nameHint` are the contact this recording belongs to - for a
     * synced call, the number that was actually dialled. The server matches on
     * that number, so the next call from the same person updates the same
     * customer instead of creating a duplicate.
     */
    suspend fun importAudio(
        localPath: String,
        mimeType: String,
        source: String,
        customerId: String? = null,
        phoneHint: String? = null,
        nameHint: String? = null,
    ): ApiResult<ProcessingJob?>

    suspend fun jobStatus(jobId: String): ApiResult<ProcessingJob>
    suspend fun review(jobId: String): ApiResult<ExtractionReview>
    suspend fun reanalyze(jobId: String): ApiResult<ProcessingJob>
    suspend fun apply(
        extractionId: String,
        edits: Map<String, String> = emptyMap(),
        confirmFollowUp: Boolean = true,
        followUpDueAtIso: String? = null,
        customerId: String? = null,
    ): ApiResult<ApplyExtractionResponse>
    suspend fun discard(extractionId: String): ApiResult<Unit>
    fun pendingCount(): Flow<Int>
}

interface CustomerRepository {
    suspend fun list(search: String?, status: LeadStatus?, page: Int): ApiResult<List<Customer>>
    suspend fun get(id: String): ApiResult<Customer>
    suspend fun timeline(id: String): ApiResult<CustomerTimelineDto>
}

interface LeadRepository {
    suspend fun list(status: LeadStatus?): ApiResult<List<LeadDto>>
    suspend fun funnel(): ApiResult<LeadFunnelDto>
    suspend fun updateStatus(leadId: String, status: LeadStatus): ApiResult<Unit>
    suspend fun convert(leadId: String, note: String?): ApiResult<Unit>
}

interface FollowUpRepository {
    suspend fun board(mineOnly: Boolean): ApiResult<FollowUpBoard>
    suspend fun markDone(id: String): ApiResult<Unit>
    suspend fun reschedule(id: String, dueAtIso: String): ApiResult<Unit>
    suspend fun cancel(id: String): ApiResult<Unit>
    suspend fun create(
        customerId: String,
        type: FollowUpType,
        title: String,
        dueAtIso: String,
    ): ApiResult<FollowUp>
}

interface ReportRepository {
    suspend fun dashboard(): ApiResult<DashboardSnapshot>
    suspend fun daily(): ApiResult<DailyReportDto>
    suspend fun weekly(): ApiResult<PeriodReportDto>
    suspend fun monthly(): ApiResult<PeriodReportDto>
}

interface AssistantRepository {
    suspend fun ask(query: String, confirmToken: String? = null): ApiResult<AssistantResponseDto>
}

interface WhatsAppRepository {
    suspend fun draft(customerId: String): ApiResult<WhatsAppDraftDto>
    suspend fun send(messageId: String, editedBody: String?): ApiResult<Unit>
}
