"""Versioned, intentionally restrictive automation ingress and action contracts."""
import base64
import binascii
from datetime import date
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class JobKind(StrEnum):
    GRAPH_MESSAGE = 'GRAPH_MESSAGE'
    GRAPH_LIFECYCLE = 'GRAPH_LIFECYCLE'
    N8N_DOCUMENT = 'N8N_DOCUMENT'
    SHAREPOINT_ARCHIVE = 'SHAREPOINT_ARCHIVE'
    HUBSPOT_CONTACT = 'HUBSPOT_CONTACT'
    OUTLOOK_DRAFT = 'OUTLOOK_DRAFT'
    TEAMS_NOTIFY = 'TEAMS_NOTIFY'
    TEAMS_APPROVAL_NOTIFY = 'TEAMS_APPROVAL_NOTIFY'


class N8NIngress(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=8, max_length=160)
    subject: str = Field(default='', max_length=250)
    sender: str = Field(default='', max_length=254)
    filename: str = Field(default='incoming-order.txt', max_length=180)
    content_base64: str | None = Field(default=None, max_length=21_000_000)
    body_text: str | None = Field(default=None, max_length=100_000)

    @model_validator(mode='after')
    def require_content(self):
        if not self.content_base64 and not self.body_text:
            raise ValueError('Either document content_base64 or body_text is required.')
        return self

    def document_bytes(self, limit: int) -> bytes:
        if self.content_base64:
            try:
                raw = base64.b64decode(self.content_base64, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError('Invalid base64 document.') from exc
        else:
            raw = (self.body_text or '').encode('utf-8')
        if not raw or len(raw) > limit:
            raise ValueError('Document is empty or exceeds the configured upload limit.')
        return raw


class ExternalSchedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sharepoint: bool = True
    hubspot: bool = False
    outlook_draft: bool = False
    teams_notify: bool = False
    # Must be explicitly verified by a human; never infer an email from PO text.
    verified_contact_email: str | None = Field(default=None, max_length=254)
    confirm_external_data_transfer: bool = False

    @field_validator('verified_contact_email')
    @classmethod
    def check_email(cls, value):
        if value and (value.count('@') != 1 or any(ch.isspace() for ch in value)):
            raise ValueError('Provide a verified recipient email address.')
        return value

    @model_validator(mode='after')
    def validation(self):
        if not self.confirm_external_data_transfer:
            raise ValueError('Operator must expressly authorize external data transfer.')
        if (self.hubspot or self.outlook_draft) and not self.verified_contact_email:
            raise ValueError('HubSpot and Outlook require a human-verified contact email.')
        if not any((self.sharepoint, self.hubspot, self.outlook_draft, self.teams_notify)):
            raise ValueError('Select at least one integration step.')
        return self


class VoiceChangeIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=8, max_length=160)
    call_id: str = Field(min_length=6, max_length=180)
    transaction_public_id: str = Field(pattern=r'^TXN-[0-9]{4}-[0-9]{6}$')
    request_type: str
    request_note: str = Field(min_length=8, max_length=1500)

    @field_validator('request_type')
    @classmethod
    def limited_types(cls, value):
        if value not in {'CALLBACK', 'DELIVERY_CHANGE', 'QUANTITY_CHANGE', 'GENERAL_QUERY'}:
            raise ValueError('Unsupported voice action; automatic modifications are prohibited.')
        return value


class VoiceDecisionIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    decision: str
    note: str = Field(min_length=3, max_length=1000)

    @field_validator('decision')
    @classmethod
    def limited(cls, v):
        if v not in {'ACKNOWLEDGED', 'DECLINED'}:
            raise ValueError('This endpoint only acknowledges or declines; amendments require a separate controlled workflow.')
        return v


class ReconcileRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operator_note: str = Field(min_length=12, max_length=1000)
    remote_id: str | None = Field(default=None, max_length=240)
    confirm_manual_review: bool = False

    @model_validator(mode='after')
    def verify_confirmation(self):
        if not self.confirm_manual_review:
            raise ValueError('Only an operator who investigated the saved/remote state may reconcile.')
        return self
