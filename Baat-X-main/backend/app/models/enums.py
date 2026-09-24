from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SALESPERSON = "salesperson"


class BusinessVertical(StrEnum):
    REAL_ESTATE = "real_estate"
    AUTOMOBILE = "automobile"
    RETAIL = "retail"
    SERVICES = "services"
    GENERIC = "generic"


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    FOLLOW_UP = "follow_up"
    HOT = "hot"
    CONVERTED = "converted"
    LOST = "lost"


FUNNEL_ORDER: dict[LeadStatus, int] = {
    LeadStatus.NEW: 0, LeadStatus.CONTACTED: 1, LeadStatus.INTERESTED: 2,
    LeadStatus.FOLLOW_UP: 3, LeadStatus.HOT: 4, LeadStatus.CONVERTED: 5, LeadStatus.LOST: 6,
}


class PurchaseIntent(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class FollowUpType(StrEnum):
    CALL_CUSTOMER = "call_customer"
    WHATSAPP_CUSTOMER = "whatsapp_customer"
    SEND_QUOTATION = "send_quotation"
    SEND_EMAIL = "send_email"
    MEET_CUSTOMER = "meet_customer"
    CHECK_AVAILABILITY = "check_availability"
    DISCUSS_PRICE = "discuss_price"
    SCHEDULE_TEST_DRIVE = "schedule_test_drive"
    SHOW_PROPERTY = "show_property"
    SEND_DOCUMENT = "send_document"
    PAYMENT_FOLLOW_UP = "payment_follow_up"
    GENERAL_FOLLOW_UP = "general_follow_up"
    OTHER = "other"


class FollowUpStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    RESCHEDULED = "rescheduled"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class QueryCategory(StrEnum):
    PRICING = "pricing"
    AVAILABILITY = "availability"
    PRODUCT_INFO = "product_info"
    DISCOUNT = "discount"
    DELIVERY = "delivery"
    LOCATION = "location"
    FEATURES = "features"
    QUOTATION = "quotation"
    PAYMENT = "payment"
    FINANCE = "finance"
    WARRANTY = "warranty"
    SERVICE = "service"
    COMPARISON = "comparison"
    COMPETITOR = "competitor"
    TIMELINE = "timeline"
    OTHER = "other"


class ConversationSource(StrEnum):
    TELL_AI = "tell_ai"
    IMPORT_CALL_RECORDING = "import_call_recording"
    IMPORT_AUDIO = "import_audio"
    MANUAL = "manual"


class JobStatus(StrEnum):
    QUEUED = "queued"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    EXTRACTING = "extracting"
    AWAITING_REVIEW = "awaiting_review"
    APPLIED = "applied"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = {JobStatus.APPLIED, JobStatus.FAILED, JobStatus.CANCELLED}


class JobStage(StrEnum):
    UPLOADING = "Uploading audio..."
    UNDERSTANDING = "Understanding conversation..."
    EXTRACTING_CUSTOMER = "Extracting customer details..."
    FINDING_FOLLOWUPS = "Finding follow-ups..."
    PREPARING_UPDATE = "Preparing CRM update..."
    DONE = "Ready for review"


class NotificationType(StrEnum):
    FOLLOW_UP_DUE = "follow_up_due"
    FOLLOW_UP_UPCOMING = "follow_up_upcoming"
    FOLLOW_UP_OVERDUE = "follow_up_overdue"
    CALLBACK_REMINDER = "callback_reminder"
    QUOTATION_REMINDER = "quotation_reminder"
    MEETING_REMINDER = "meeting_reminder"
    PAYMENT_FOLLOW_UP = "payment_follow_up"
    CUSTOMER_REQUESTED_CALLBACK = "customer_requested_callback"
    JOB_READY = "job_ready"
    JOB_FAILED = "job_failed"


class WhatsAppMessageStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    DISCARDED = "discarded"


class SubscriptionPlan(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    BUSINESS = "business"
