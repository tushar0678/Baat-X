package com.baatx.data.remote.dto

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Wire types for organizations, teams, members and invitations.
 *
 * `permissions` is mirrored to the client only so the UI can hide buttons the
 * user can't use. It is never an authorization source - the server re-checks
 * membership and permissions on every single request.
 */

@Serializable
data class OrganizationSummaryDto(
    val id: String,
    val name: String,
    val vertical: String = "generic",
    val role: String,
    @SerialName("is_current") val isCurrent: Boolean = false,
)

@Serializable
data class OrganizationDto(
    val id: String,
    val name: String,
    val vertical: String = "generic",
    @SerialName("country_code") val countryCode: String = "IN",
    val timezone: String = "Asia/Kolkata",
    @SerialName("default_currency") val defaultCurrency: String = "INR",
    val role: String,
    val permissions: List<String> = emptyList(),
)

@Serializable
data class CreateOrganizationRequest(
    val name: String,
    val vertical: String = "generic",
    @SerialName("country_code") val countryCode: String = "IN",
    val timezone: String = "Asia/Kolkata",
    @SerialName("default_currency") val defaultCurrency: String = "INR",
)

@Serializable
data class TeamDto(
    val id: String,
    val name: String,
    val description: String? = null,
    @SerialName("lead_user_id") val leadUserId: String? = null,
    @SerialName("parent_team_id") val parentTeamId: String? = null,
    @SerialName("member_count") val memberCount: Int = 0,
)

@Serializable
data class CreateTeamRequest(
    val name: String,
    val description: String? = null,
    @SerialName("lead_user_id") val leadUserId: String? = null,
    @SerialName("parent_team_id") val parentTeamId: String? = null,
)

@Serializable
data class MemberDto(
    @SerialName("user_id") val userId: String,
    @SerialName("membership_id") val membershipId: String,
    @SerialName("full_name") val fullName: String,
    val email: String? = null,
    val role: String,
    @SerialName("team_id") val teamId: String? = null,
    @SerialName("job_title") val jobTitle: String? = null,
)

@Serializable
data class UpdateMemberRequest(
    val role: String? = null,
    @SerialName("team_id") val teamId: String? = null,
    @SerialName("job_title") val jobTitle: String? = null,
)

@Serializable
data class InviteMemberRequest(
    val email: String? = null,
    val phone: String? = null,
    val role: String = "member",
    @SerialName("team_id") val teamId: String? = null,
    @SerialName("job_title") val jobTitle: String? = null,
)

@Serializable
data class InvitationDto(
    val id: String,
    val email: String? = null,
    val phone: String? = null,
    val role: String,
    @SerialName("team_id") val teamId: String? = null,
    val status: String,
    @SerialName("expires_at") val expiresAt: String,
    // Returned once, to whoever created the invite, so it can be shared.
    val token: String? = null,
)

@Serializable
data class AcceptInvitationRequest(
    val token: String,
)
