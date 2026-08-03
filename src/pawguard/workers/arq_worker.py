"""ARQ worker entrypoint. Run with: `arq pawguard.workers.arq_worker.WorkerSettings`."""

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from pawguard.core.config import get_settings
from pawguard.core.logging import configure_logging

# Import every module's models so their string-referenced relationships (e.g.
# "...DogProfile") resolve in this process. The web app gets this via
# api/v1/router.py pulling in every router; the worker process doesn't, so
# without this the first scheduled job that queries a model with a joined
# relationship crashes with InvalidRequestError at mapper configuration.
from pawguard.modules.adoption import models as adoption_models  # noqa: F401
from pawguard.modules.auth import models as auth_models  # noqa: F401
from pawguard.modules.dog import models as dog_models  # noqa: F401
from pawguard.modules.donation import models as donation_models  # noqa: F401
from pawguard.modules.finance import models as finance_models  # noqa: F401
from pawguard.modules.fleet import models as fleet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.grievance import models as grievance_models  # noqa: F401
from pawguard.modules.inventory import models as inventory_models  # noqa: F401
from pawguard.modules.lost_found import models as lost_found_models  # noqa: F401
from pawguard.modules.medical import models as medical_models  # noqa: F401
from pawguard.modules.notifications import models as notification_models  # noqa: F401
from pawguard.modules.portal import models as portal_models  # noqa: F401
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.settings import models as settings_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.storage import models as storage_models  # noqa: F401
from pawguard.modules.volunteer import models as volunteer_models  # noqa: F401
from pawguard.workers.jobs.email_jobs import (
    send_email_verification_email_job,
    send_notification_email_job,
    send_password_reset_email_job,
)
from pawguard.workers.jobs.fleet_jobs import (
    check_equipment_checkout_expiry,
    check_fleet_maintenance_due,
    check_vehicle_insurance_expiry,
)
from pawguard.workers.jobs.scheduled_jobs import (
    check_grievance_sla_escalation,
    check_inventory_expiry,
    check_inventory_low_stock,
    check_vaccination_renewals,
    post_adoption_followups,
    process_recurring_donation_charges,
    process_sponsorship_charges,
    send_post_service_feedback_surveys,
)

settings = get_settings()


async def startup(ctx: dict[str, object]) -> None:
    configure_logging()


class WorkerSettings:
    functions: list[Any] = [
        send_password_reset_email_job,
        send_email_verification_email_job,
        send_notification_email_job,
        check_inventory_low_stock,
        check_inventory_expiry,
        check_vaccination_renewals,
        post_adoption_followups,
        process_sponsorship_charges,
        process_recurring_donation_charges,
        send_post_service_feedback_surveys,
        check_fleet_maintenance_due,
        check_vehicle_insurance_expiry,
        check_equipment_checkout_expiry,
        check_grievance_sla_escalation,
    ]
    cron_jobs = [
        cron(check_inventory_low_stock, hour={0, 12}, minute={0}),
        cron(check_inventory_expiry, hour={9}, minute={0}),
        cron(check_vaccination_renewals, hour={9}, minute={30}),
        cron(post_adoption_followups, hour={10}, minute={0}),
        cron(send_post_service_feedback_surveys, hour={10}, minute={30}),
        cron(process_sponsorship_charges, hour=8, minute=0),
        cron(process_recurring_donation_charges, hour=8, minute=15),
        cron(check_fleet_maintenance_due, hour=7, minute=0),
        cron(check_vehicle_insurance_expiry, hour=7, minute=30),
        cron(check_equipment_checkout_expiry, hour=7, minute=45),
        cron(check_grievance_sla_escalation, hour={0, 12}, minute={15}),
    ]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
