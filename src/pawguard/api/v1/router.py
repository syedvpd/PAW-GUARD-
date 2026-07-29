"""Aggregates every module's router under the versioned API prefix."""

from fastapi import APIRouter

from pawguard.modules.admin.dashboard_router import admin_dashboard_router
from pawguard.modules.auth.admin_router import admin_router
from pawguard.modules.auth.router import router as auth_router
from pawguard.modules.rescue.router import router as rescue_router
from pawguard.modules.dog.router import router as dog_router
from pawguard.modules.adoption.router import router as adoption_router
from pawguard.modules.volunteer.router import router as volunteer_router
from pawguard.modules.foster.router import router as foster_router
from pawguard.modules.donation.router import router as donation_router
from pawguard.modules.lost_found.router import router as lost_found_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(admin_dashboard_router)
api_v1_router.include_router(rescue_router)
api_v1_router.include_router(dog_router)
api_v1_router.include_router(adoption_router)
api_v1_router.include_router(volunteer_router)
api_v1_router.include_router(foster_router)
api_v1_router.include_router(donation_router)
api_v1_router.include_router(lost_found_router)
