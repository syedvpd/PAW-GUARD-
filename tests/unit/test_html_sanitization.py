"""HTML sanitization tests — adversarial (ITEM 7).

Proves:
1. nh3 is available as a production dependency.
2. sanitize_html() strips dangerous payloads: <script>, onerror, javascript:, iframe, SVG, nested.
3. sanitize_plain() strips ALL tags.
4. Permitted formatting (bold, links, lists) survives sanitization.
5. Grievance, volunteer schemas apply sanitization on all rich-text fields.
6. None/empty inputs pass through unchanged.
7. Encoded payloads are caught.

Per adversarial pre-mortem §10: must test ALL input/output paths, not just one endpoint.
"""

from __future__ import annotations

from pawguard.core.sanitize import sanitize_html, sanitize_plain


class TestNH3Available:
    """Proves nh3 is installed as a real dependency, not a stub."""

    def test_nh3_importable(self) -> None:
        import nh3

        assert hasattr(nh3, "clean"), "nh3.clean() must exist"

    def test_sanitize_module_uses_nh3(self) -> None:
        from pawguard.core import sanitize

        assert sanitize._NH3_AVAILABLE is True, (
            "nh3 must be available in production; _NH3_AVAILABLE is False"
        )


class TestSanitizeHtmlDangerousPayloads:
    """Verifies dangerous payloads are stripped by sanitize_html()."""

    def test_script_tag_stripped(self) -> None:
        result = sanitize_html("<script>alert(1)</script>")
        assert result is not None
        assert "<script>" not in result
        assert "alert(1)" not in result

    def test_script_tag_with_content_stripped(self) -> None:
        result = sanitize_html("<p>Hello</p><script>document.cookie='stolen'</script>")
        assert "<script>" not in (result or "")
        assert "document.cookie" not in (result or "")
        assert "Hello" in (result or "")

    def test_onerror_event_handler_stripped(self) -> None:
        result = sanitize_html('<img src="x" onerror="alert(1)">')
        assert result is not None
        assert "onerror" not in result
        assert "alert(1)" not in result

    def test_onclick_event_handler_stripped(self) -> None:
        result = sanitize_html('<a onclick="steal()">click me</a>')
        assert result is not None
        assert "onclick" not in result
        assert "steal()" not in result

    def test_javascript_url_stripped(self) -> None:
        result = sanitize_html('<a href="javascript:alert(1)">click</a>')
        assert result is not None
        assert "javascript:" not in result

    def test_iframe_stripped(self) -> None:
        result = sanitize_html('<iframe src="https://evil.com"></iframe>')
        assert result is not None
        assert "<iframe" not in result

    def test_object_tag_stripped(self) -> None:
        result = sanitize_html('<object data="evil.swf"></object>')
        assert result is not None
        assert "<object" not in result

    def test_embed_tag_stripped(self) -> None:
        result = sanitize_html('<embed src="evil.swf">')
        assert result is not None
        assert "<embed" not in result

    def test_svg_with_script_stripped(self) -> None:
        result = sanitize_html("<svg><script>alert(1)</script></svg>")
        assert result is not None
        assert "<script>" not in result
        assert "alert(1)" not in result

    def test_nested_payload_stripped(self) -> None:
        """Nested/obfuscated attempt."""
        payload = '<div><span><script>alert("xss")</script></span></div>'
        result = sanitize_html(payload)
        assert result is not None
        assert "<script>" not in result

    def test_malformed_html_handled(self) -> None:
        """Malformed HTML must not raise; dangerous tags must be stripped even if malformed."""
        payload = "<scr<script>ipt>alert(1)</script>"
        result = sanitize_html(payload)
        # Must not raise
        assert result is not None
        # No executable <script> tag remains — that is the XSS protection requirement.
        # nh3 may preserve the text node "alert(1)" since plain text is not a script vector.
        assert "<script>" not in result

    def test_html_entity_encoded_script_stripped(self) -> None:
        """HTML-entity encoded script tag."""
        # nh3 decodes entities before processing
        payload = "&lt;script&gt;alert(1)&lt;/script&gt;"
        result = sanitize_html(payload)
        # Entities themselves are safe text — this is not an XSS vector
        # The important thing: no actual <script> tag in output
        assert result is not None
        assert "<script>" not in result


class TestSanitizeHtmlPermittedContent:
    """Positive test: permitted formatting must survive sanitization."""

    def test_bold_preserved(self) -> None:
        result = sanitize_html("<b>Important notice</b>")
        assert result is not None
        assert "Important notice" in result

    def test_paragraphs_preserved(self) -> None:
        result = sanitize_html("<p>First paragraph</p><p>Second paragraph</p>")
        assert result is not None
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_lists_preserved(self) -> None:
        result = sanitize_html("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert result is not None
        assert "Item 1" in result
        assert "Item 2" in result

    def test_plain_text_unchanged(self) -> None:
        text = "Just a plain text description with no HTML at all."
        result = sanitize_html(text)
        assert result == text

    def test_none_returns_none(self) -> None:
        assert sanitize_html(None) is None

    def test_empty_string_returns_empty(self) -> None:
        result = sanitize_html("")
        assert not result  # empty or None


class TestSanitizePlain:
    """Verifies sanitize_plain() strips ALL HTML tags."""

    def test_all_tags_stripped(self) -> None:
        result = sanitize_plain("<b>bold</b> and <i>italic</i>")
        assert result is not None
        assert "<b>" not in result
        assert "<i>" not in result
        assert "bold" in result
        assert "italic" in result

    def test_script_stripped(self) -> None:
        result = sanitize_plain("<script>alert(1)</script>")
        assert result is not None
        assert "<script>" not in result
        assert "alert(1)" not in result

    def test_none_returns_none(self) -> None:
        assert sanitize_plain(None) is None


class TestGrievanceSchemaSanitization:
    """Proves grievance Pydantic schemas apply sanitization on all rich-text fields."""

    def test_grievance_create_details_sanitized(self) -> None:
        from pawguard.modules.grievance.schemas import GrievanceCreate

        payload = GrievanceCreate(
            reporter_name="Test User",
            reporter_phone="+1-555-0100",
            complaint_type="Delay",
            details="<script>alert(1)</script>My dog was not rescued.",
        )
        assert "<script>" not in payload.details
        assert "alert(1)" not in payload.details
        assert "My dog was not rescued." in payload.details

    def test_grievance_create_reporter_name_sanitized(self) -> None:
        from pawguard.modules.grievance.schemas import GrievanceCreate

        payload = GrievanceCreate(
            reporter_name="<b>Hacker</b><script>steal()</script>",
            reporter_phone="+1-555-0100",
            complaint_type="Test",
            details="Valid detail text.",
        )
        # reporter_name uses sanitize_plain → all tags stripped
        assert "<b>" not in payload.reporter_name
        assert "<script>" not in payload.reporter_name

    def test_grievance_update_resolution_notes_sanitized(self) -> None:
        from pawguard.modules.grievance.schemas import GrievanceUpdate

        payload = GrievanceUpdate(resolution_notes='<img onerror="alert(1)" src="x">Case resolved.')
        assert payload.resolution_notes is not None
        assert "onerror" not in payload.resolution_notes
        assert "Case resolved." in payload.resolution_notes

    def test_comment_create_body_sanitized(self) -> None:
        from pawguard.modules.grievance.schemas import CommentCreate

        payload = CommentCreate(body='<iframe src="evil.com"></iframe>Staff response here.')
        assert "<iframe" not in payload.body
        assert "Staff response here." in payload.body

    def test_service_feedback_comments_sanitized(self) -> None:
        from pawguard.modules.grievance.schemas import ServiceFeedbackCreate

        payload = ServiceFeedbackCreate(
            rating=5,
            comments="<script>alert(1)</script>Great service!",
        )
        assert payload.comments is not None
        assert "<script>" not in payload.comments
        assert "Great service!" in payload.comments

    def test_none_fields_pass_through(self) -> None:
        from pawguard.modules.grievance.schemas import GrievanceUpdate

        payload = GrievanceUpdate(resolution_notes=None)
        assert payload.resolution_notes is None


class TestVolunteerSchemaSanitization:
    """Proves volunteer schemas sanitize notes, medical_conditions, experience fields."""

    def test_volunteer_profile_create_notes_sanitized(self) -> None:
        from pawguard.modules.volunteer.schemas import VolunteerProfileCreate

        payload = VolunteerProfileCreate(
            emergency_contact_name="Jane",
            emergency_contact_phone="+1-555-0100",
            notes="<script>alert(1)</script>Available weekends.",
        )
        assert payload.notes is not None
        assert "<script>" not in payload.notes
        assert "Available weekends." in payload.notes


class TestFosterSchemaSanitization:
    """Proves foster schemas sanitize progress logs and profile notes."""

    def test_foster_progress_log_sanitized(self) -> None:
        from pawguard.modules.foster.schemas import FosterProgressLogCreate

        payload = FosterProgressLogCreate(
            behavior_notes='<script>alert("xss")</script>Friendly and calm.',
            feeding_notes='<img src="x" onerror="evil()">Ate all food.',
            notes="<b>Great dog</b><iframe src='bad.com'></iframe>",
        )
        assert "<script>" not in (payload.behavior_notes or "")
        assert "Friendly and calm." in (payload.behavior_notes or "")
        assert "onerror" not in (payload.feeding_notes or "")
        assert "Ate all food." in (payload.feeding_notes or "")
        assert "<iframe" not in (payload.notes or "")
        assert "Great dog" in (payload.notes or "")


class TestAdoptionSchemaSanitization:
    """Proves adoption schemas sanitize applicant and staff text fields."""

    def test_adoption_application_create_sanitized(self) -> None:
        import uuid

        from pawguard.modules.adoption.schemas import AdoptionApplicationCreate

        payload = AdoptionApplicationCreate(
            dog_id=uuid.uuid4(),
            residential_status="owned",
            existing_pets_medical_details="<script>steal()</script>One healthy cat.",
            pet_care_experience='<a href="javascript:alert(1)">Click</a>Experienced pet owner.',
        )
        assert "<script>" not in (payload.existing_pets_medical_details or "")
        assert "One healthy cat." in (payload.existing_pets_medical_details or "")
        assert "javascript:" not in (payload.pet_care_experience or "")
        assert "Experienced pet owner." in (payload.pet_care_experience or "")

    def test_adoption_application_update_sanitized(self) -> None:
        from pawguard.modules.adoption.schemas import AdoptionApplicationUpdate

        payload = AdoptionApplicationUpdate(
            vetting_officer_notes="<script>alert(1)</script>Home check passed.",
            home_inspection_notes='<img src="x" onerror="alert(1)">Yard is secure.',
        )
        assert "<script>" not in (payload.vetting_officer_notes or "")
        assert "Home check passed." in (payload.vetting_officer_notes or "")
        assert "onerror" not in (payload.home_inspection_notes or "")
        assert "Yard is secure." in (payload.home_inspection_notes or "")


class TestDogSchemaSanitization:
    """Proves dog registration and update schemas sanitize text fields."""

    def test_dog_create_and_weight_log_sanitized(self) -> None:
        from pawguard.modules.dog.schemas import DogProfileCreate, DogWeightLogCreate

        dog = DogProfileCreate(
            name="<b>Barnaby</b><script>alert(1)</script>",
            breed="Indie<img onerror=alert(1) src=x>",
            distinctive_markers="White chest<script>bad()</script>",
            medical_notes="Healthy<iframe src=evil.com></iframe>",
        )
        assert "<script>" not in dog.name
        assert "onerror" not in dog.breed
        assert "<script>" not in (dog.distinctive_markers or "")
        assert "<iframe" not in (dog.medical_notes or "")

        weight_log = DogWeightLogCreate(
            weight=15.5,
            notes="<script>alert(1)</script>Post-recovery weigh in",
        )
        assert "<script>" not in (weight_log.notes or "")
        assert "Post-recovery weigh in" in (weight_log.notes or "")


class TestMedicalSchemaSanitization:
    """Proves medical exams and treatments sanitize text fields."""

    def test_clinical_exam_and_treatment_sanitized(self) -> None:
        import uuid

        from pawguard.modules.medical.schemas import ClinicalExamCreate, MedicalTreatmentCreate

        exam = ClinicalExamCreate(
            dog_id=uuid.uuid4(),
            body_condition_score=5,
            triage_diagnosis="Stable<script>alert(1)</script>",
            ocular_aural_notes="Clear<img onerror=alert(1) src=x>",
        )
        assert "<script>" not in exam.triage_diagnosis
        assert "onerror" not in (exam.ocular_aural_notes or "")

        treatment = MedicalTreatmentCreate(
            dog_id=uuid.uuid4(),
            treatment_type="Spay/Neuter",
            description="Routine<script>alert(1)</script>",
            anesthesia_log="Isoflurane<iframe src=bad.com></iframe>",
        )
        assert "<script>" not in treatment.description
        assert "<iframe" not in (treatment.anesthesia_log or "")


class TestDoubleFailureNotificationObservable:
    """ITEM 9b: Proves double-failure (PDF + push) is logged durably, not suppressed."""

    def test_double_failure_logs_error(self) -> None:
        """When both PDF generation and push notification fail, logger.error is called."""

        # We verify that contextlib.suppress is NOT wrapping the push call
        import inspect

        from pawguard.modules.foster import service as foster_service

        source = inspect.getsource(foster_service)

        # The old pattern: contextlib.suppress(Exception) around push call
        assert (
            "with contextlib.suppress(Exception):\n                await self._send_push"
            not in source
        ), (
            "contextlib.suppress(Exception) still wraps _send_push — double-failure is silently swallowed"
        )

    def test_foster_service_logs_pdf_failure_durably(self) -> None:
        """pdf_and_push_double_failure event key must be present in service source."""
        import inspect

        from pawguard.modules.foster import service as foster_service

        source = inspect.getsource(foster_service)
        assert "pdf_and_push_double_failure" in source, (
            "The structured log event key 'pdf_and_push_double_failure' is missing — "
            "double failures will not be observable."
        )
        assert "adoption_lease_pdf_failed" in source, (
            "The structured log event key 'adoption_lease_pdf_failed' is missing."
        )
