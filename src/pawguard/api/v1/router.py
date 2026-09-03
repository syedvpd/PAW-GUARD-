"""Aggregates every module's router under the versioned API prefix."""

from fastapi import APIRouter

from pawguard.modules.admin.audit_router import audit_router
from pawguard.modules.admin.dashboard_router import admin_dashboard_router
from pawguard.modules.adoption.router import router as adoption_router
from pawguard.modules.auth.admin_router import admin_router
from pawguard.modules.auth.router import router as auth_router
from pawguard.modules.companion_pet.router import router as companion_pet_router
from pawguard.modules.dashboards.router import router as dashboards_router
from pawguard.modules.dog.router import router as dog_router
from pawguard.modules.donation.router import router as donation_router
from pawguard.modules.finance.router import router as finance_router
from pawguard.modules.fleet.router import router as fleet_router
from pawguard.modules.foster.router import router as foster_router
from pawguard.modules.grievance.router import router as grievance_router
from pawguard.modules.inventory.router import router as inventory_router
from pawguard.modules.lost_found.router import router as lost_found_router
from pawguard.modules.medical.router import router as medical_router
from pawguard.modules.notifications.admin_router import admin_router as admin_notifications_router
from pawguard.modules.notifications.router import router as notification_router
from pawguard.modules.portal.router import router as portal_router
from pawguard.modules.reports.router import router as reports_router
from pawguard.modules.rescue.router import public_rescue_router
from pawguard.modules.rescue.router import router as rescue_router
from pawguard.modules.rescue_centre.router import router as rescue_centre_router
from pawguard.modules.settings.router import router as settings_router
from pawguard.modules.shelter.router import router as shelter_router
from pawguard.modules.storage import router as storage_router
from pawguard.modules.volunteer.router import router as volunteer_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(admin_router)
api_v1_router.include_router(admin_notifications_router)
api_v1_router.include_router(dashboards_router)
api_v1_router.include_router(admin_dashboard_router)
api_v1_router.include_router(audit_router)
api_v1_router.include_router(rescue_router)
api_v1_router.include_router(public_rescue_router)
api_v1_router.include_router(rescue_centre_router)
api_v1_router.include_router(dog_router)
api_v1_router.include_router(companion_pet_router)

api_v1_router.include_router(adoption_router)
api_v1_router.include_router(volunteer_router)
api_v1_router.include_router(foster_router, prefix="/fosters")
api_v1_router.include_router(foster_router, prefix="/foster")
api_v1_router.include_router(donation_router)
api_v1_router.include_router(lost_found_router)
api_v1_router.include_router(inventory_router)
api_v1_router.include_router(shelter_router)
api_v1_router.include_router(medical_router)
api_v1_router.include_router(portal_router)
api_v1_router.include_router(fleet_router)
api_v1_router.include_router(grievance_router)
api_v1_router.include_router(notification_router)
api_v1_router.include_router(settings_router)
api_v1_router.include_router(storage_router)
api_v1_router.include_router(finance_router)
api_v1_router.include_router(reports_router)
