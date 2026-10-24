"""Versioned business inputs shared by API validation and local analytical tools."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.intelligence.contracts import AnalysisContext, PositiveInt, StrictModel, decimal_number

Text = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
Short = Annotated[str, Field(strict=True, min_length=1, max_length=100)]

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
        if set(self.provenance) != set(BusinessFields.model_fields):
            raise ValueError('profile_provenance_required')
        return self
