// ---------------- CRM ----------------
// Matches backend/app/schemas/crm.py -> CustomerResponse field-for-field.
// `ignoreUnknownKeys = true` (set in NetworkModule's Json config) means the
// server can add fields later without another round of this exercise - it's
// only a field the client actively tries to read/deserialize as the wrong
// type, or a required backend field with no local counterpart, that breaks
// parsing. `normalized_phone` was exactly that: the backend always sends it,
// but it wasn't declared here at all, and unlike unknown-key tolerance,
// Decimal-typed money fields (budget_min/budget_max) can arrive as JSON
// strings depending on the server's encoder - so they're kept as String? and
// parsed to Double on demand rather than declared Double? directly.
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
}