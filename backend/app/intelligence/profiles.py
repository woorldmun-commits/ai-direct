"""Versioned business inputs shared by API validation and local analytical tools."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.intelligence.contracts import AnalysisContext, PositiveInt, StrictModel, decimal_number
from app.sources.conversion import ATTRIBUTION_DIRECT_CODE

Text = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
Short = Annotated[str, Field(strict=True, min_length=1, max_length=100)]

class EvaluationPolicy(StrictModel):
    counter_id: PositiveInt
    goal_ids: Annotated[tuple[PositiveInt, ...], Field(min_length=1, max_length=10)]
    attribution: str
    conversion_stage: Literal['lead', 'qualified_lead', 'appointment', 'visit', 'sale']
    conversion_lag_days: Annotated[int, Field(strict=True, ge=0, le=3650)]
    minimum_conversions: Annotated[int, Field(strict=True, ge=1, le=1000)]

    @field_validator('goal_ids')
    @classmethod
    def ordered_goals(cls, value):
        if tuple(sorted(set(value))) != value:
            raise ValueError('canonical_goal_ids_required')
        return value

    @field_validator('attribution')
    @classmethod
    def known_attribution(cls, value):
        if value not in ATTRIBUTION_DIRECT_CODE:
            raise ValueError('unknown_attribution')
        return value


class BusinessFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Short
    industry_code: Short
    business_model: Literal['b2b', 'b2c']
    products: Annotated[list[Short], Field(max_length=30)]
    geography: Annotated[list[Short], Field(max_length=30)]
    currency: Literal['RUB']
    timezone: Literal['Europe/Moscow']
    goal: Text
    conversion_definition: Short
    average_order_value: Decimal | None = None
    gross_margin_pct: Decimal | None = None
    sales_cycle_days: Annotated[int, Field(strict=True, ge=0, le=3650)] | None = None
    budget_limit: Decimal | None = None
    seasonality: Text | None = None
    advantages: Annotated[list[Short], Field(max_length=30)]
    crm_available: StrictBool
    evaluation_policy: EvaluationPolicy | None = None

    @field_validator('average_order_value', 'gross_margin_pct', 'budget_limit', mode='before')
    @classmethod
    def numeric(cls, raw):
        value = decimal_number(raw)
        if value is not None and (value < 0 or value > Decimal('999999999999')):
            raise ValueError('amount_bounds')
        return value

    @field_validator('gross_margin_pct')
    @classmethod
    def margin(cls, value):
        if value is not None and value > 100:
            raise ValueError('margin_bounds')
        return value



class FieldProvenance(StrictModel):
    origin: Literal['user_confirmed']
    actor_id: PositiveInt
    updated_at: datetime

    @field_validator('updated_at')
    @classmethod
    def aware(cls, value):
        return AnalysisContext.aware(value)


class BusinessProfile(StrictModel):
    revision: PositiveInt
    fields: BusinessFields
    provenance: dict[str, FieldProvenance]

    @model_validator(mode='after')
    def complete_provenance(self):
        required = set(BusinessFields.model_fields) - {'evaluation_policy'}
        if self.fields.evaluation_policy is not None:
            required.add('evaluation_policy')
        if not required <= set(self.provenance) <= set(BusinessFields.model_fields):
            raise ValueError('profile_provenance_required')
        return self
