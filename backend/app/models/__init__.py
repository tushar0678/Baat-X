"""SQLAlchemy models for BaatX.

Every tenant-scoped table carries ``business_id`` and is indexed on it; the
repository layer refuses to build a query without it.
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.billing import Subscription, UsageRecord
from app.models.conversation import AIExtraction, AIProcessingJob, ConversationEvent
from app.models.crm import ConversionEvent, Customer, Lead, LeadStatusTransition
from app.models.followup import FollowUp, Notification, Task
from app.models.reports import QueryCategoryStat, ReportMetric, ReportSnapshot
from app.models.tenancy import Business, BusinessMembership, Invitation, Team, User
from app.models.whatsapp import WhatsAppMessage

__all__ = [
    "AIExtraction",
    "AIProcessingJob",
    "AuditLog",
    "Base",
    "Business",
    "BusinessMembership",
    "ConversationEvent",
    "ConversionEvent",
    "Customer",
    "FollowUp",
    "Invitation",
    "Lead",
    "LeadStatusTransition",
    "Notification",
    "QueryCategoryStat",
    "ReportMetric",
    "ReportSnapshot",
    "Subscription",
    "Task",
    "Team",
    "UsageRecord",
    "User",
    "WhatsAppMessage",
]