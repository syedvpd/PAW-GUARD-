"""Pydantic schemas for the Foster Management module."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pawguard.modules.auth.schemas import UserProfile
from pawguard.modules.dog.schemas import DogProfileResponse
from pawguard.modules.foster.models import (
    FosterPlacementStatus,
    FosterStatus,
    SupplyItemType,
)


class FosterProgressLogCreate(BaseModel):
    weight_kg: float | None = Field(None, ge=0, le=999.99, examples=[16.4])
    behavior_notes: str | None = Field(
        None, examples=["Playful and settled well, no anxiety signs."]
    )
    feeding_notes: str | None = Field(None, examples=["Ate full portion, no leftovers."])
    medication_notes: str | None = Field(
        None, examples=["Gave morning antibiotic dose on schedule."]
    )
    exercise_minutes: int | None = Field(None, ge=0, examples=[30])
    photo_urls: list[str] | None = Field(None, examples=[["https://example.com/foster/day1.jpg"]])
    mood_rating: int | None = Field(None, ge=1, le=5, examples=[4])
    notes: str | None = Field(None, examples=["Doing great overall."])

    @field_validator("weight_kg", mode="before")
    @classmethod
    def normalize_weight(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return None
            try:
                return float(v_clean)
            except ValueError:
                return None
        return v

    @field_validator("exercise_minutes", "mood_rating", mode="before")
    @classmethod
    def normalize_ints(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return None
            try:
                return int(v_clean)
            except ValueError:
                return None
        return v

    @field_validator("photo_urls", mode="before")
    @classmethod
    def normalize_photos(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip()
            if v_clean == "":
                return []
            return [v_clean]
        return v


class FosterProgressLogResponse(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    tracked_by_id: uuid.UUID
    weight_kg: float | None
    behavior_notes: str | None
    feeding_notes: str | None
    medication_notes: str | None
    exercise_minutes: int | None
    photo_urls: list[str] | None
    mood_rating: int | None
    notes: str | None
    logged_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FosterProfileCreate(BaseModel):
    preferences: str | None = Field(None, examples=["Puppies, Medical Recovery"])
    max_capacity: int = Field(1, ge=1, examples=[2])
    notes: str | None = Field(None, examples=["Fenced backyard, prior fostering experience."])


class FosterProfileUpdate(BaseModel):
    status: FosterStatus | None = Field(None, examples=["approved"])
    preferences: str | None = Field(None, examples=["Senior Dogs"])
    max_capacity: int | None = Field(None, examples=[2])
    is_available: bool | None = Field(None, examples=[True])
    notes: str | None = Field(None, examples=["Home inspection passed on 2026-07-20."])

    # Vetting & Background Verification
    background_check_passed: bool | None = Field(None, examples=[True])
    background_check_notes: str | None = Field(None, examples=["Background check clear."])
    references_checked: bool | None = Field(None, examples=[True])
    reference_notes: str | None = Field(None, examples=["References verified."])
    vetting_notes: str | None = Field(None, examples=["Background check clear."])
    vetted_at: datetime | None = Field(None)

    # Home Inspection
    home_inspection_passed: bool | None = Field(None, examples=[True])
    home_inspection_notes: str | None = Field(None, examples=["Fenced yard verified."])
    home_inspection_address: str | None = Field(None, examples=["123 Shelter Way"])
    inspected_at: datetime | None = Field(None)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            return v_clean
        return v

    @field_validator("vetted_at", "inspected_at", mode="before")
    @classmethod
    def normalize_empty_datetimes(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator(
        "background_check_passed",
        "references_checked",
        "home_inspection_passed",
        "is_available",
        mode="before",
    )
    @classmethod
    def normalize_booleans(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ("true", "1", "yes", "passed", "cleared", "approved"):
                return True
            if v_clean in ("false", "0", "no", "failed", "rejected", "flagged"):
                return False
            if v_clean in ("", "none", "null", "pending", "unverified", "in_progress"):
                return None
        return v


class FosterProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: FosterStatus
    preferences: str | None
    max_capacity: int
    active_count: int
    is_available: bool
    notes: str | None

    # Vetting & Background Verification
    background_check_passed: bool | None = None
    background_check_status: str = "pending"
    background_check_notes: str | None = None
    references_checked: bool | None = None
    reference_notes: str | None = None
    vetting_notes: str | None = None
    vetted_at: datetime | None = None

    # Home Inspection
    home_inspection_passed: bool | None = None
    home_inspection_status: str = "pending"
    home_inspection_notes: str | None = None
    home_inspection_address: str | None = None
    inspected_at: datetime | None = None
    home_inspection_details: dict[str, Any] | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    user: UserProfile | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def safe_from_orm(cls, data: Any) -> Any:
        if not isinstance(data, dict) and hasattr(data, "__dict__"):
            user_val = None
            if "user" in data.__dict__ and data.__dict__["user"] is not None:
                user_val = data.__dict__["user"]
            elif hasattr(data, "user"):
                try:
                    user_val = data.user
                except Exception:
                    user_val = None

            return {
                "id": getattr(data, "id", None),
                "user_id": getattr(data, "user_id", None),
                "status": getattr(data, "status", FosterStatus.APPLIED),
                "preferences": getattr(data, "preferences", None),
                "max_capacity": getattr(data, "max_capacity", 1),
                "active_count": getattr(data, "active_count", 0),
                "is_available": getattr(data, "is_available", True),
                "notes": getattr(data, "notes", None),
                "background_check_passed": getattr(data, "background_check_passed", None),
                "background_check_notes": getattr(data, "background_check_notes", None),
                "references_checked": getattr(data, "references_checked", None),
                "reference_notes": getattr(data, "reference_notes", None),
                "vetting_notes": getattr(data, "vetting_notes", None),
                "vetted_at": getattr(data, "vetted_at", None),
                "home_inspection_passed": getattr(data, "home_inspection_passed", None),
                "home_inspection_notes": getattr(data, "home_inspection_notes", None),
                "home_inspection_address": getattr(data, "home_inspection_address", None),
                "inspected_at": getattr(data, "inspected_at", None),
                "home_inspection_details": getattr(data, "home_inspection_details", None),
                "created_at": getattr(data, "created_at", None),
                "updated_at": getattr(data, "updated_at", None),
                "user": user_val,
            }
        return data

    def model_post_init(self, __context: Any) -> None:
        if self.background_check_passed is True:
            self.background_check_status = "cleared"
        elif self.background_check_passed is False:
            if self.background_check_notes and "flag" in self.background_check_notes.lower():
                self.background_check_status = "flagged"
            else:
                self.background_check_status = "rejected"
        elif self.vetted_at is not None:
            self.background_check_status = "initiated"
        else:
            self.background_check_status = "pending"

        if self.home_inspection_passed is True:
            self.home_inspection_status = "approved"
        elif self.home_inspection_passed is False:
            self.home_inspection_status = "rejected"
        elif self.inspected_at is not None:
            self.home_inspection_status = "inspected"
        elif self.home_inspection_address is not None or (
            self.home_inspection_notes and "scheduled" in self.home_inspection_notes.lower()
        ):
            self.home_inspection_status = "scheduled"
        else:
            self.home_inspection_status = "pending"


class FosterWeightLogCreate(BaseModel):
    weight_kg: float = Field(..., gt=0, le=999.99, examples=[18.5])
    notes: str | None = Field(None, examples=["Weekly weigh-in on digital scale"])


class FosterBehaviorLogCreate(BaseModel):
    behavior_notes: str = Field(
        ..., min_length=1, examples=["Settling in nicely, responds well to recall commands."]
    )
    mood_rating: int | None = Field(None, ge=1, le=5, examples=[4])
    exercise_minutes: int | None = Field(None, ge=0, examples=[45])
    notes: str | None = Field(None)


class FosterMedicationLogCreate(BaseModel):
    medication_notes: str = Field(
        ..., min_length=1, examples=["Administered prescribed morning dose with meal."]
    )
    verified: bool = Field(True)
    notes: str | None = Field(None)


class FosterMediaLogCreate(BaseModel):
    photo_urls: list[str] = Field(
        ..., min_length=1, examples=[["https://storage.pawguard.org/dogs/foster_day3.jpg"]]
    )
    caption: str | None = Field(None, examples=["Playing fetch in the fenced yard"])
    notes: str | None = Field(None)


class FosterBackgroundCheckInitiate(BaseModel):
    provider: str | None = Field(None, examples=["Checkr", "Internal Vetting"])
    notes: str | None = Field(None, examples=["Initiating criminal and identity verification"])

    @model_validator(mode="before")
    @classmethod
    def flex_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        prov = (
            d.get("provider")
            or d.get("verification_provider")
            or d.get("id_type")
            or d.get("identity_provider")
            or d.get("service")
            or d.get("service_name")
        )
        if prov:
            d["provider"] = str(prov).strip()
        nts = (
            d.get("notes")
            or d.get("dispatch_notes")
            or d.get("reference_notes")
            or d.get("comments")
            or d.get("details")
        )
        if nts:
            d["notes"] = str(nts).strip()
        return d


class FosterBackgroundCheckOutcome(BaseModel):
    outcome: str = Field("cleared", examples=["cleared", "flagged", "rejected"])
    notes: str = Field(
        "Background check outcome recorded.",
        examples=["Identity verified, no disqualifying records found."],
    )
    references_checked: bool = Field(True)
    reference_notes: str | None = Field(None, examples=["Two personal references verified."])

    @model_validator(mode="before")
    @classmethod
    def flex_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Outcome alias resolution
        raw_outcome = (
            d.get("outcome")
            or d.get("decision")
            or d.get("status")
            or d.get("outcome_decision")
            or "cleared"
        )
        if isinstance(raw_outcome, str):
            low = raw_outcome.strip().lower()
            if any(k in low for k in ("clear", "pass", "approve")):
                d["outcome"] = "cleared"
            elif any(k in low for k in ("flag", "discrepancy", "audit")):
                d["outcome"] = "flagged"
            elif any(k in low for k in ("reject", "fail")):
                d["outcome"] = "rejected"
            else:
                d["outcome"] = low
        else:
            d["outcome"] = "cleared"

        # Notes alias resolution
        raw_notes = (
            d.get("notes")
            or d.get("verification_notes")
            or d.get("outcome_notes")
            or d.get("notes_verification_id")
            or d.get("details")
            or d.get("rejection_reason")
        )
        if raw_notes and isinstance(raw_notes, str) and raw_notes.strip():
            d["notes"] = raw_notes.strip()
        else:
            d["notes"] = "Background check outcome recorded."

        # References checked alias
        ref_val = d.get("references_checked") or d.get("personal_vet_references_checked")
        if ref_val is not None:
            if isinstance(ref_val, str):
                d["references_checked"] = ref_val.strip().lower() in ("true", "1", "yes", "checked")
            else:
                d["references_checked"] = bool(ref_val)

        return d


class FosterHomeInspectionSchedule(BaseModel):
    scheduled_at: datetime = Field(..., examples=["2026-09-10T14:00:00Z"])
    inspector_id: uuid.UUID | None = Field(None)
    inspector_name: str | None = Field(None, examples=["Sarah Jenkins"])
    inspection_type: str = Field("physical", examples=["physical", "virtual"])
    address: str | None = Field(None, examples=["742 Evergreen Terrace, Paw City"])
    notes: str | None = Field(None)

    @model_validator(mode="before")
    @classmethod
    def flex_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        # Inspector alias
        insp = d.get("inspector_name") or d.get("assigned_inspector") or d.get("inspector")
        if insp:
            d["inspector_name"] = str(insp).strip()
        # Address alias
        addr = d.get("address") or d.get("inspection_site_address") or d.get("site_address")
        if addr:
            d["address"] = str(addr).strip()
        # Notes alias
        nts = d.get("notes") or d.get("scheduling_notes") or d.get("access_instructions")
        if nts:
            d["notes"] = str(nts).strip()

        # Type normalization
        itype = d.get("inspection_type") or "physical"
        if isinstance(itype, str):
            low = itype.lower()
            if "virtual" in low:
                d["inspection_type"] = "virtual"
            else:
                d["inspection_type"] = "physical"

        # Scheduled date parser
        sched = d.get("scheduled_at") or d.get("scheduled_date") or d.get("date")
        if isinstance(sched, str) and sched.strip():
            raw_s = sched.strip()
            # Try parsing various date formats
            for fmt in (
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M",
                "%Y-%m-%d",
                "%d-%m-%Y",
            ):
                try:
                    dt = datetime.strptime(raw_s, fmt)
                    d["scheduled_at"] = dt.isoformat()
                    break
                except ValueError:
                    pass
        return d


class FosterHomeInspectionLog(BaseModel):
    yard_condition: str | None = Field(None, examples=["Spacious grassy yard, clean"])
    fencing_condition: str | None = Field(
        None, examples=["6ft cedar privacy fence, secure gate latch"]
    )
    household_info: str | None = Field(None, examples=["2 adults, 1 child (age 10)"])
    existing_pets_info: str | None = Field(None, examples=["1 vaccinated senior cat"])
    hazards: str | None = Field(None, examples=["None observed, pool securely enclosed"])
    rating: int | None = Field(None, ge=1, le=5, examples=[5])
    evidence_urls: list[str] | None = Field(
        None, examples=[["https://storage.pawguard.org/inspections/fence.jpg"]]
    )
    notes: str | None = Field(None, examples=["Excellent home setup, ready for high-energy foster"])


class FosterHomeInspectionOutcome(BaseModel):
    outcome: str = Field("approved", examples=["approved", "rejected"])
    notes: str = Field(
        "Home inspection completed.",
        examples=["Meets all physical security and home care standards."],
    )
    address: str | None = Field(None)

    @model_validator(mode="before")
    @classmethod
    def flex_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        raw_out = d.get("outcome") or d.get("decision") or d.get("status") or "approved"
        if isinstance(raw_out, str):
            low = raw_out.lower()
            if any(k in low for k in ("reject", "fail")):
                d["outcome"] = "rejected"
            else:
                d["outcome"] = "approved"
        return d


class FosterRejectPayload(BaseModel):
    notes: str | None = Field(None, examples=["Caregiver declined home inspection"])
    reason: str | None = Field(None)
    rejection_reason: str | None = Field(None)
    vetting_notes: str | None = Field(None)
    status: str | None = Field(None)


class FosterPlacementCreate(BaseModel):
    dog_id: uuid.UUID
    notes: str | None = Field(None, examples=["Placing for post-surgery recovery, 4-6 weeks."])
    vet_exception: bool = Field(
        False,
        description=(
            "A veterinarian's medical exception override, used when the dog has no "
            "approved medical clearance but a vet judges it foster-eligible anyway. "
            "Only usable by a caller holding medical:clearance; requires exception_notes."
        ),
    )
    exception_notes: str | None = Field(
        None, max_length=1000, description="Required when vet_exception is set."
    )

    @model_validator(mode="after")
    def _require_exception_justification(self) -> "FosterPlacementCreate":
        if self.vet_exception and not (self.exception_notes and self.exception_notes.strip()):
            raise ValueError("exception_notes is required when vet_exception is set.")
        return self


class FosterPlacementResponse(BaseModel):
    id: uuid.UUID
    foster_id: uuid.UUID
    dog_id: uuid.UUID
    placed_at: datetime
    returned_at: datetime | None = None
    is_active: bool = True
    status: FosterPlacementStatus = FosterPlacementStatus.ACTIVE
    adoption_application_id: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime | None = None
    dog: DogProfileResponse | None = None
    foster: "FosterProfileResponse | None" = None
    foster_name: str | None = None
    dog_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def safe_from_orm(cls, data: Any) -> Any:
        if not isinstance(data, dict) and hasattr(data, "__dict__"):
            dog_val = None
            if "dog" in data.__dict__ and data.__dict__["dog"] is not None:
                dog_val = data.__dict__["dog"]
            elif hasattr(data, "dog"):
                try:
                    dog_val = data.dog
                except Exception:
                    dog_val = None

            foster_val = None
            if "foster" in data.__dict__ and data.__dict__["foster"] is not None:
                foster_val = data.__dict__["foster"]
            elif hasattr(data, "foster"):
                try:
                    foster_val = data.foster
                except Exception:
                    foster_val = None

            return {
                "id": getattr(data, "id", None),
                "foster_id": getattr(data, "foster_id", None),
                "dog_id": getattr(data, "dog_id", None),
                "placed_at": getattr(data, "placed_at", None),
                "returned_at": getattr(data, "returned_at", None),
                "is_active": getattr(data, "is_active", True),
                "status": getattr(data, "status", FosterPlacementStatus.ACTIVE),
                "adoption_application_id": getattr(data, "adoption_application_id", None),
                "notes": getattr(data, "notes", None),
                "created_at": getattr(data, "created_at", None),
                "dog": dog_val,
                "foster": foster_val,
                "foster_name": getattr(data, "foster_name", None),
                "dog_name": getattr(data, "dog_name", None),
            }
        return data

    @model_validator(mode="after")
    def populate_names(self) -> "FosterPlacementResponse":
        if self.dog and not self.dog_name and hasattr(self.dog, "name"):
            self.dog_name = self.dog.name
        if (
            self.foster
            and self.foster.user
            and not self.foster_name
            and hasattr(self.foster.user, "full_name")
        ):
            self.foster_name = self.foster.user.full_name
        return self


class FosterReturnRequest(BaseModel):
    notes: str | None = Field(None, examples=["Fully recovered, ready to return to shelter."])
    reason: str | None = Field(None, examples=["Foster period completed", "Shelter request"])


class FosterVetCheckRequest(BaseModel):
    reason: str | None = Field(None, examples=["Routine health check", "Lethargy and limping"])
    urgency: str = Field("routine", examples=["routine", "urgent", "emergency"])
    preferred_date: datetime | None = Field(None)
    notes: str | None = Field(None, examples=["Dog showing slight limp on front left paw."])

    @field_validator("urgency", mode="before")
    @classmethod
    def normalize_urgency(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_clean = v.strip().lower()
            return v_clean if v_clean in ("routine", "urgent", "emergency") else "routine"
        return "routine"

    @field_validator("preferred_date", mode="before")
    @classmethod
    def normalize_preferred_date(cls, v: Any) -> Any:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v


class FosterVetCheckResponse(BaseModel):
    placement_id: uuid.UUID
    dog_id: uuid.UUID
    foster_id: uuid.UUID
    reason: str
    urgency: str
    status: str
    requested_at: datetime
    message: str


class FosterSupplyDispatchCreate(BaseModel):
    item_type: SupplyItemType
    description: str | None = Field(None, examples=["20lb bag of puppy food"])
    quantity: int = Field(1, ge=1, examples=[1])


class FosterSupplyDispatchResponse(BaseModel):
    id: uuid.UUID
    placement_id: uuid.UUID
    dispatched_by_id: uuid.UUID
    item_type: SupplyItemType
    description: str | None
    quantity: int
    dispatched_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
