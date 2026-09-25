package com.baatx.data.repository

import com.baatx.core.connectivity.ConnectivityObserver
import com.baatx.core.network.ApiResult
import com.baatx.core.network.map
import com.baatx.core.network.safeApiCall
import com.baatx.core.org.OrgContext
import com.baatx.core.security.TokenStore
import com.baatx.data.local.PendingCaptureDao
import com.baatx.data.local.PendingCaptureEntity
import com.baatx.data.remote.*
import com.baatx.data.remote.dto.*
import com.baatx.domain.model.*
import com.baatx.domain.repository.*
import com.baatx.work.SyncScheduler
import java.io.File
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

@Singleton
class AuthRepositoryImpl @Inject constructor(
    private val api: AuthApi,
    private val tokenStore: TokenStore,
    private val orgContext: OrgContext,
) : AuthRepository {

    override val isSignedIn: Flow<Boolean> = tokenStore.isSignedIn

    override suspend fun login(email: String, password: String): ApiResult<UserProfileDto> =
        safeApiCall { api.login(LoginRequest(email.trim().lowercase(), password)) }
            .map { it.persist() }

    override suspend fun signup(
        fullName: String,
        email: String,
        password: String,
        businessName: String,
        vertical: String,
    ): ApiResult<UserProfileDto> = safeApiCall {
        api.signup(
            SignupRequest(
                fullName = fullName.trim(),
                email = email.trim().lowercase(),
                password = password,
                businessName = businessName.trim(),
                vertical = vertical,
            ),
        )
    }.map { it.persist() }

    private fun TokenResponse.persist(): UserProfileDto {
        val businessId = activeBusinessId ?: user.businesses.firstOrNull()?.id
        tokenStore.save(
            access = accessToken,
            refresh = refreshToken,
            businessId = businessId,
            userName = user.fullName,
        )

        val business = user.businesses.firstOrNull { it.id == businessId }
        if (businessId != null && business != null) {
            orgContext.switchTo(
                orgId = businessId,
                orgName = business.name,
                role = business.role,
                permissions = emptySet(),
            )
        }
        return user
    }

    override fun signOut() {
        tokenStore.clear()
        orgContext.clear()
    }

    override fun currentUserName(): String? = tokenStore.userName
}

@Singleton
class ConversationRepositoryImpl @Inject constructor(
    private val api: AiApi,
    private val dao: PendingCaptureDao,
    private val connectivity: ConnectivityObserver,
    private val syncScheduler: SyncScheduler,
) : ConversationRepository {

    override suspend fun tellAi(
        text: String,
        customerId: String?,
        phoneHint: String?,
    ): ApiResult<ProcessingJob?> {
        val key = UUID.randomUUID().toString()
        dao.insert(
            PendingCaptureEntity(
                id = key,
                idempotencyKey = key,
                kind = "tell_ai",
                text = text,
                customerId = customerId,
                phoneHint = phoneHint,
            ),
        )

        if (!connectivity.currentlyOnline()) {
            syncScheduler.requestImmediateSync()
            return ApiResult.Success(null)
        }

        val result = safeApiCall {
            api.tellAi(
                TellAIRequest(
                    text = text,
                    idempotencyKey = key,
                    customerId = customerId,
                    phoneHint = phoneHint,
                ),
            )
        }
        when (result) {
            is ApiResult.Success -> dao.delete(key)
            is ApiResult.Failure -> syncScheduler.requestImmediateSync()
        }
        return result.map { it.toDomain() }
    }

    override suspend fun importAudio(
        localPath: String,
        mimeType: String,
        source: String,
        customerId: String?,
        phoneHint: String?,
        nameHint: String?,
    ): ApiResult<ProcessingJob?> {
        val key = UUID.randomUUID().toString()
        dao.insert(
            PendingCaptureEntity(
                id = key,
                idempotencyKey = key,
                kind = source,
                localAudioPath = localPath,
                mimeType = mimeType,
                customerId = customerId,
                phoneHint = phoneHint,
                nameHint = nameHint,
            ),
        )

        if (!connectivity.currentlyOnline()) {
            syncScheduler.requestImmediateSync()
            return ApiResult.Success(null)
        }

        val file = File(localPath)
        val part = MultipartBody.Part.createFormData(
            "file",
            file.name,
            file.asRequestBody(mimeType.toMediaTypeOrNull()),
        )
        val plain = "text/plain".toMediaTypeOrNull()

        val result = safeApiCall {
            api.processAudio(
                file = part,
                idempotencyKey = key.toRequestBody(plain),
                source = source.toRequestBody(plain),
                customerId = customerId?.toRequestBody(plain),
                phoneHint = phoneHint?.takeIf { it.isNotBlank() }?.toRequestBody(plain),
                nameHint = nameHint?.takeIf { it.isNotBlank() }?.toRequestBody(plain),
            )
        }

        if (result is ApiResult.Success) {
            dao.delete(key)
            file.delete()
        } else {
            syncScheduler.requestImmediateSync()
        }
        return result.map { it.toDomain() }
    }

    override suspend fun jobStatus(jobId: String) =
        safeApiCall { api.jobStatus(jobId) }.map { it.toDomain() }

    override suspend fun review(jobId: String) =
        safeApiCall { api.review(jobId) }.map { it.toDomain() }

    override suspend fun reanalyze(jobId: String) =
        safeApiCall { api.reanalyze(jobId) }.map { it.toDomain() }

    override suspend fun apply(
        extractionId: String,
        edits: Map<String, String>,
        confirmFollowUp: Boolean,
        followUpDueAtIso: String?,
        customerId: String?,
    ) = safeApiCall {
        api.apply(
            extractionId,
            ApplyExtractionRequest(
                customerId = customerId,
                editedFields = edits,
                confirmFollowUp = confirmFollowUp,
                followUpDueAt = followUpDueAtIso,
            ),
        )
    }

    override suspend fun discard(extractionId: String): ApiResult<Unit> =
        safeApiCall { api.apply(extractionId, ApplyExtractionRequest(discard = true)) }.map { }

    override fun pendingCount(): Flow<Int> = dao.observePendingCount()
}

@Singleton
class CustomerRepositoryImpl @Inject constructor(
    private val api: CrmApi,
) : CustomerRepository {

    override suspend fun list(search: String?, status: LeadStatus?, page: Int) =
        safeApiCall {
            api.customers(
                search = search?.takeIf { it.isNotBlank() },
                leadStatus = status?.apiValue,
                page = page,
            )
        }.map { result -> result.items.map { it.toDomain() } }

    override suspend fun get(id: String) =
        safeApiCall { api.customer(id) }.map { it.toDomain() }

    override suspend fun timeline(id: String) = safeApiCall { api.timeline(id) }
}

@Singleton
class LeadRepositoryImpl @Inject constructor(
    private val api: CrmApi,
) : LeadRepository {

    override suspend fun list(status: LeadStatus?) =
        safeApiCall { api.leads(status = status?.apiValue) }.map { it.items }

    override suspend fun funnel() = safeApiCall { api.funnel() }

    override suspend fun updateStatus(leadId: String, status: LeadStatus): ApiResult<Unit> =
        safeApiCall {
            api.updateLeadStatus(leadId, mapOf("status" to status.apiValue))
        }.map { }

    override suspend fun convert(leadId: String, note: String?): ApiResult<Unit> =
        safeApiCall {
            api.convert(leadId, buildMap { note?.let { put("note", it) } })
        }.map { }
}

@Singleton
class FollowUpRepositoryImpl @Inject constructor(
    private val api: FollowUpApi,
) : FollowUpRepository {

    override suspend fun board(mineOnly: Boolean) =
        safeApiCall { api.board(mineOnly) }.map { it.toDomain() }

    override suspend fun markDone(id: String): ApiResult<Unit> =
        safeApiCall {
            api.update(id, FollowUpUpdateRequest(status = "completed"))
        }.map { }

    override suspend fun reschedule(id: String, dueAtIso: String): ApiResult<Unit> =
        safeApiCall {
            api.update(id, FollowUpUpdateRequest(dueAt = dueAtIso))
        }.map { }

    override suspend fun cancel(id: String): ApiResult<Unit> =
        safeApiCall {
            api.update(id, FollowUpUpdateRequest(status = "cancelled"))
        }.map { }

    override suspend fun create(
        customerId: String,
        type: FollowUpType,
        title: String,
        dueAtIso: String,
    ) = safeApiCall {
        api.create(
            FollowUpCreateRequest(
                customerId = customerId,
                type = type.apiValue,
                title = title,
                dueAt = dueAtIso,
            ),
        )
    }.map { it.toDomain() }
}

@Singleton
class ReportRepositoryImpl @Inject constructor(
    private val api: ReportApi,
) : ReportRepository {
    override suspend fun dashboard() = safeApiCall { api.dashboard() }.map { it.toDomain() }
    override suspend fun daily() = safeApiCall { api.daily() }
    override suspend fun weekly() = safeApiCall { api.weekly() }
    override suspend fun monthly() = safeApiCall { api.monthly() }
}

@Singleton
class AssistantRepositoryImpl @Inject constructor(
    private val api: AssistantApi,
) : AssistantRepository {
    override suspend fun ask(query: String, confirmToken: String?) =
        safeApiCall { api.query(AssistantQueryRequest(query, confirmToken)) }
}

@Singleton
class WhatsAppRepositoryImpl @Inject constructor(
    private val api: WhatsAppApi,
) : WhatsAppRepository {

    override suspend fun draft(customerId: String) =
        safeApiCall { api.draft(WhatsAppDraftRequest(customerId)) }

    override suspend fun send(messageId: String, editedBody: String?): ApiResult<Unit> =
        safeApiCall {
            api.send(
                WhatsAppSendRequest(
                    messageId = messageId,
                    approved = true,
                    editedBody = editedBody,
                ),
            )
        }.map { }
}

@Singleton
class OrganizationRepositoryImpl @Inject constructor(
    private val api: OrganizationApi,
) : OrganizationRepository {

    override suspend fun myOrganizations() =
        safeApiCall { api.myOrganizations() }

    override suspend fun current() =
        safeApiCall { api.current() }

    override suspend fun activate(organizationId: String) =
        safeApiCall { api.activate(organizationId) }

    override suspend fun createOrganization(name: String, vertical: String) =
        safeApiCall {
            api.createOrganization(CreateOrganizationRequest(name, vertical))
        }

    override suspend fun teams() = safeApiCall { api.teams() }

    override suspend fun createTeam(name: String, leadUserId: String?) =
        safeApiCall {
            api.createTeam(
                CreateTeamRequest(
                    name = name,
                    leadUserId = leadUserId,
                ),
            )
        }

    override suspend fun members() = safeApiCall { api.members() }

    override suspend fun updateMember(
        membershipId: String,
        role: String?,
        teamId: String?,
    ) = safeApiCall {
        api.updateMember(
            membershipId,
            UpdateMemberRequest(
                role = role,
                teamId = teamId,
            ),
        )
    }

    override suspend fun removeMember(membershipId: String): ApiResult<Unit> =
        safeApiCall { api.removeMember(membershipId) }.map { }

    override suspend fun invite(
        contact: String,
        role: String,
        teamId: String?,
    ) = safeApiCall {
        api.invite(
            if (contact.contains("@")) {
                InviteMemberRequest(
                    email = contact,
                    role = role,
                    teamId = teamId,
                )
            } else {
                InviteMemberRequest(
                    phone = contact,
                    role = role,
                    teamId = teamId,
                )
            },
        )
    }

    override suspend fun acceptInvitation(token: String) =
        safeApiCall {
            api.acceptInvitation(
                AcceptInvitationRequest(token = token),
            )
        }
}
