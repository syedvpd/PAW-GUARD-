"""Locust load test for PawGuard backend."""

from locust import HttpUser, between, task


class PublicUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def list_dogs(self):
        self.client.get("/api/v1/dogs?page=1&size=20", name="/api/v1/dogs")

    @task(2)
    def portal_landing(self):
        self.client.get("/api/v1/portal/landing-stats", name="/api/v1/portal/landing-stats")

    @task(1)
    def submit_rescue_report(self):
        self.client.post("/api/v1/public/rescue/report", json={
            "reporter_name": "Load Tester", "reporter_phone": "+919876543210",
            "reporter_email": "load@test.com", "location": {"address": "Load St", "latitude": 17.4, "longitude": 78.4},
            "number_of_dogs": 1, "animal_condition": "stray", "description": "Load test"
        }, name="/api/v1/public/rescue/report")

    @task(1)
    def submit_adoption_application(self):
        self.client.post("/api/v1/adoption/applications", json={
            "dog_id": "00000000-0000-0000-0000-000000000000",
            "applicant_name": "Load Tester", "applicant_email": "load@test.com",
            "applicant_phone": "+919876543210"
        }, name="/api/v1/adoption/applications")
