package com.baatx.data.remote

import com.baatx.data.remote.dto.AcceptInvitationRequest
import com.baatx.data.remote.dto.CreateOrganizationRequest
import com.baatx.data.remote.dto.CreateTeamRequest
import com.baatx.data.remote.dto.InvitationDto
import com.baatx.data.remote.dto.InviteMemberRequest
import com.baatx.data.remote.dto.MemberDto
import com.baatx.data.remote.dto.OrganizationDto
import com.baatx.data.remote.dto.OrganizationSummaryDto
import com.baatx.data.remote.dto.TeamDto
import com.baatx.data.remote.dto.UpdateMemberRequest
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Organizations, teams, members and invitations.
 *
 * Note `activate()`: it passes an explicit `X-Organization-Id` header rather
 * than relying on the interceptor, because at that moment `OrgContext` still
 * points at the *previous* organization. The server treats the header as
 * untrusted input either way - it only honours it if an active membership
 * backs it, so a tampered value gets a 403 rather than another tenant's data.
 */
interface OrganizationApi {

    @GET("api/v1/organizations")
    suspend fun myOrganizations(): List<OrganizationSummaryDto>

    @GET("api/v1/organizations/current")
    suspend fun current(): OrganizationDto

    /** Reads an organization by explicitly asking for it - used when switching. */
    @GET("api/v1/organizations/current")
    suspend fun activate(
        @Header("X-Organization-Id") organizationId: String,
    ): OrganizationDto

    @POST("api/v1/organizations")
    suspend fun createOrganization(
        @Body body: CreateOrganizationRequest,
    ): OrganizationDto

    @GET("api/v1/organizations/teams")
    suspend fun teams(): List<TeamDto>

    @POST("api/v1/organizations/teams")
    suspend fun createTeam(@Body body: CreateTeamRequest): TeamDto

    @GET("api/v1/organizations/members")
    suspend fun members(): List<MemberDto>

    @PATCH("api/v1/organizations/members/{membershipId}")
    suspend fun updateMember(
        @Path("membershipId") membershipId: String,
        @Body body: UpdateMemberRequest,
    ): MemberDto

    @DELETE("api/v1/organizations/members/{membershipId}")
    suspend fun removeMember(@Path("membershipId") membershipId: String)

    @POST("api/v1/organizations/invitations")
    suspend fun invite(@Body body: InviteMemberRequest): InvitationDto

    @POST("api/v1/organizations/invitations/accept")
    suspend fun acceptInvitation(@Body body: AcceptInvitationRequest): OrganizationDto
}
