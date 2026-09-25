package com.baatx.domain.repository

import com.baatx.core.network.ApiResult
import com.baatx.data.remote.dto.InvitationDto
import com.baatx.data.remote.dto.MemberDto
import com.baatx.data.remote.dto.OrganizationDto
import com.baatx.data.remote.dto.OrganizationSummaryDto
import com.baatx.data.remote.dto.TeamDto

interface OrganizationRepository {

    /** Organizations this user actually belongs to - powers the switcher. */
    suspend fun myOrganizations(): ApiResult<List<OrganizationSummaryDto>>

    suspend fun current(): ApiResult<OrganizationDto>

    /**
     * Switches context. Re-reads role and permissions from the server rather
     * than trusting the switcher's cached summary, so what the UI enables is
     * always the server's current answer.
     */
    suspend fun activate(organizationId: String): ApiResult<OrganizationDto>

    suspend fun createOrganization(name: String, vertical: String): ApiResult<OrganizationDto>

    suspend fun teams(): ApiResult<List<TeamDto>>

    suspend fun createTeam(name: String, leadUserId: String?): ApiResult<TeamDto>

    suspend fun members(): ApiResult<List<MemberDto>>

    suspend fun updateMember(
        membershipId: String,
        role: String? = null,
        teamId: String? = null,
    ): ApiResult<MemberDto>

    suspend fun removeMember(membershipId: String): ApiResult<Unit>

    /** `contact` may be an email or a phone number; the server decides which. */
    suspend fun invite(contact: String, role: String, teamId: String?): ApiResult<InvitationDto>

    suspend fun acceptInvitation(token: String): ApiResult<OrganizationDto>
}
