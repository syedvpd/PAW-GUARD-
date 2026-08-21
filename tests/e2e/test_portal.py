"""E2E tests for PORTAL module (51 endpoints)."""

import uuid

import pytest
from tests.e2e.factories import TEST
from tests.e2e.helpers import call, uid


@pytest.mark.asyncio
class TestPortalPublicEndpoints:
    """Public portal endpoints."""

    async def test_portal_stats(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/stats", expected=200)

    async def test_portal_blog(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/blog", expected=200)

    async def test_portal_faq(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/faq", expected=200)

    async def test_portal_contact(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/contact", expected=200)

    async def test_portal_legal(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/legal", expected=200)

    async def test_portal_success_stories(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/success-stories", expected=200)

    async def test_portal_urgent_alerts(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/urgent-alerts", expected=200)

    async def test_portal_transparency(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/transparency", expected=200)

    async def test_portal_veterinary_network(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/veterinary-network", expected=200)

    async def test_portal_me_dashboard(self, client, setup):
        await call(
            client,
            "portal",
            "GET",
            "/api/v1/portal/me/dashboard",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_portal_blog_slug(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/blog",
            json={
                "title": f"Blog_{uid()}",
                "content": "Test blog post content",
                "status": "published",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            slug = create_r.json()["data"].get("slug", "test")
            await call(client, "portal", "GET", f"/api/v1/portal/blog/slug/{slug}", expected=200)

    async def test_portal_legal_slug(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/legal",
            json={
                "title": f"Legal_{uid()}",
                "content": "Legal content",
                "document_type": "privacy_policy",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            slug = create_r.json()["data"].get("slug", "privacy")
            await call(client, "portal", "GET", f"/api/v1/portal/legal/{slug}", expected=200)

    async def test_portal_success_story_detail(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/success-stories",
            json={
                "title": f"Story_{uid()}",
                "content": "Success story content",
                "dog_name": "Buddy",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            story_id = create_r.json()["data"]["id"]
            await call(
                client, "portal", "GET", f"/api/v1/portal/success-stories/{story_id}", expected=200
            )


@pytest.mark.asyncio
class TestPortalCmsEndpoints:
    """CMS page endpoints."""

    async def test_portal_cms_page(self, client, setup):
        await call(
            client,
            "portal",
            "GET",
            "/api/v1/portal/admin/cms/pages",
            headers=setup.admin_headers,
            expected=200,
        )


@pytest.mark.asyncio
class TestPortalAdminBlogEndpoints:
    """Admin blog management endpoints."""

    async def test_create_blog_post(self, client, setup):
        r = await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/blog",
            headers=setup.admin_headers,
            json={
                "title": f"Blog_{uid()}",
                "content": "Test content",
                "status": "draft",
            },
            expected=201,
        )
        TEST.blog_post_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_admin_blog(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/blog",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_blog_post(self, client, setup):
        if hasattr(TEST, "blog_post_id") and TEST.blog_post_id:
            post_id = str(TEST.blog_post_id)
        else:
            create_r = await client.post(
                "/api/v1/portal/admin/blog",
                json={
                    "title": f"Blog_{uid()}",
                    "content": "Update content",
                    "status": "draft",
                },
                headers=setup.admin_headers,
            )
            post_id = create_r.json()["data"]["id"]
        await call(
            client,
            "portal_admin",
            "PUT",
            f"/api/v1/portal/admin/blog/{post_id}",
            headers=setup.admin_headers,
            json={
                "title": "Updated Blog",
            },
            expected=200,
        )

    async def test_delete_blog_post(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/blog",
            json={
                "title": f"DelBlog_{uid()}",
                "content": "To delete",
                "status": "draft",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            post_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "DELETE",
                f"/api/v1/portal/admin/blog/{post_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_bulk_delete_blog(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/blog",
            json={
                "title": f"BulkBlog_{uid()}",
                "content": "Bulk delete",
                "status": "draft",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            post_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/blog/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [post_id],
                },
                expected=200,
            )

    async def test_bulk_status_blog(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/blog",
            json={
                "title": f"StatBlog_{uid()}",
                "content": "Bulk status",
                "status": "draft",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            post_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/blog/bulk/status",
                headers=setup.admin_headers,
                json={
                    "ids": [post_id],
                    "status": "published",
                },
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminFaqEndpoints:
    """Admin FAQ management endpoints."""

    async def test_create_faq(self, client, setup):
        await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/faq",
            headers=setup.admin_headers,
            json={
                "question": f"Question_{uid()}?",
                "answer": "Test answer",
                "category": "general",
            },
            expected=201,
        )

    async def test_list_admin_faq(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/faq",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_faq(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/faq",
            json={
                "question": f"UpdFaq_{uid()}?",
                "answer": "Original answer",
                "category": "general",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            entry_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "PUT",
                f"/api/v1/portal/admin/faq/{entry_id}",
                headers=setup.admin_headers,
                json={
                    "answer": "Updated answer",
                },
                expected=200,
            )

    async def test_delete_faq(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/faq",
            json={
                "question": f"DelFaq_{uid()}?",
                "answer": "To delete",
                "category": "general",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            entry_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "DELETE",
                f"/api/v1/portal/admin/faq/{entry_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_bulk_delete_faq(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/faq",
            json={
                "question": f"BulkFaq_{uid()}?",
                "answer": "Bulk delete",
                "category": "general",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            entry_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/faq/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [entry_id],
                },
                expected=200,
            )

    async def test_bulk_status_faq(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/faq",
            json={
                "question": f"StatFaq_{uid()}?",
                "answer": "Bulk status",
                "category": "general",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            entry_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/faq/bulk/status",
                headers=setup.admin_headers,
                json={
                    "ids": [entry_id],
                    "status": "active",
                },
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminContactEndpoints:
    """Admin contact management endpoints."""

    async def test_create_contact(self, client, setup):
        r = await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/contact",
            headers=setup.admin_headers,
            json={
                "location_name": f"Contact_{uid()}",
                "address": "123 Contact St",
                "phone": "+1122334455",
                "email": "contact@test.com",
            },
            expected=201,
        )
        TEST.contact_location_id = uuid.UUID(r.json()["data"]["id"])

    async def test_update_contact(self, client, setup):
        if hasattr(TEST, "contact_location_id") and TEST.contact_location_id:
            location_id = str(TEST.contact_location_id)
        else:
            create_r = await client.post(
                "/api/v1/portal/admin/contact",
                json={
                    "location_name": f"UpdContact_{uid()}",
                    "address": "Upd St",
                    "phone": "+1122334455",
                    "email": "upd@test.com",
                },
                headers=setup.admin_headers,
            )
            location_id = create_r.json()["data"]["id"]
        await call(
            client,
            "portal_admin",
            "PUT",
            f"/api/v1/portal/admin/contact/{location_id}",
            headers=setup.admin_headers,
            json={
                "phone": "+9988776655",
            },
            expected=200,
        )


@pytest.mark.asyncio
class TestPortalAdminLegalEndpoints:
    """Admin legal document management endpoints."""

    async def test_create_legal(self, client, setup):
        r = await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/legal",
            headers=setup.admin_headers,
            json={
                "title": f"Legal_{uid()}",
                "content": "Legal content",
                "document_type": "privacy_policy",
            },
            expected=201,
        )
        TEST.legal_doc_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_admin_legal(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/legal",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_legal(self, client, setup):
        if hasattr(TEST, "legal_doc_id") and TEST.legal_doc_id:
            doc_id = str(TEST.legal_doc_id)
        else:
            create_r = await client.post(
                "/api/v1/portal/admin/legal",
                json={
                    "title": f"UpdLegal_{uid()}",
                    "content": "Update legal",
                    "document_type": "terms_of_service",
                },
                headers=setup.admin_headers,
            )
            doc_id = create_r.json()["data"]["id"]
        await call(
            client,
            "portal_admin",
            "PUT",
            f"/api/v1/portal/admin/legal/{doc_id}",
            headers=setup.admin_headers,
            json={
                "content": "Updated legal content",
            },
            expected=200,
        )

    async def test_delete_legal(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/legal",
            json={
                "title": f"DelLegal_{uid()}",
                "content": "To delete",
                "document_type": "refund_policy",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            doc_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "DELETE",
                f"/api/v1/portal/admin/legal/{doc_id}",
                headers=setup.admin_headers,
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminSuccessStoriesEndpoints:
    """Admin success story management endpoints."""

    async def test_create_success_story(self, client, setup):
        r = await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/success-stories",
            headers=setup.admin_headers,
            json={
                "title": f"Story_{uid()}",
                "content": "Happy adoption story",
                "dog_name": "Buddy",
            },
            expected=201,
        )
        TEST.story_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_admin_success_stories(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/success-stories",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_success_story(self, client, setup):
        if hasattr(TEST, "story_id") and TEST.story_id:
            story_id = str(TEST.story_id)
        else:
            create_r = await client.post(
                "/api/v1/portal/admin/success-stories",
                json={
                    "title": f"UpdStory_{uid()}",
                    "content": "Update story",
                    "dog_name": "Max",
                },
                headers=setup.admin_headers,
            )
            story_id = create_r.json()["data"]["id"]
        await call(
            client,
            "portal_admin",
            "PUT",
            f"/api/v1/portal/admin/success-stories/{story_id}",
            headers=setup.admin_headers,
            json={
                "content": "Updated story content",
            },
            expected=200,
        )

    async def test_delete_success_story(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/success-stories",
            json={
                "title": f"DelStory_{uid()}",
                "content": "To delete",
                "dog_name": "Luna",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            story_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "DELETE",
                f"/api/v1/portal/admin/success-stories/{story_id}",
                headers=setup.admin_headers,
                expected=200,
            )

    async def test_bulk_delete_stories(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/success-stories",
            json={
                "title": f"BulkStory_{uid()}",
                "content": "Bulk delete",
                "dog_name": "Rocky",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            story_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/success-stories/bulk/delete",
                headers=setup.admin_headers,
                json={
                    "ids": [story_id],
                },
                expected=200,
            )

    async def test_bulk_status_stories(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/success-stories",
            json={
                "title": f"StatStory_{uid()}",
                "content": "Bulk status",
                "dog_name": "Coco",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            story_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "POST",
                "/api/v1/portal/admin/success-stories/bulk/status",
                headers=setup.admin_headers,
                json={
                    "ids": [story_id],
                    "status": "published",
                },
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminUrgentAlertsEndpoints:
    """Admin urgent alert management endpoints."""

    async def test_create_urgent_alert(self, client, setup):
        r = await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/urgent-alerts",
            headers=setup.admin_headers,
            json={
                "title": f"Alert_{uid()}",
                "message": "Emergency alert",
                "severity": "high",
            },
            expected=201,
        )
        TEST.alert_id = uuid.UUID(r.json()["data"]["id"])

    async def test_list_admin_urgent_alerts(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/urgent-alerts",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_urgent_alert(self, client, setup):
        if hasattr(TEST, "alert_id") and TEST.alert_id:
            alert_id = str(TEST.alert_id)
        else:
            create_r = await client.post(
                "/api/v1/portal/admin/urgent-alerts",
                json={
                    "title": f"UpdAlert_{uid()}",
                    "message": "Update alert",
                    "severity": "medium",
                },
                headers=setup.admin_headers,
            )
            alert_id = create_r.json()["data"]["id"]
        await call(
            client,
            "portal_admin",
            "PUT",
            f"/api/v1/portal/admin/urgent-alerts/{alert_id}",
            headers=setup.admin_headers,
            json={
                "message": "Updated alert message",
            },
            expected=200,
        )

    async def test_delete_urgent_alert(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/urgent-alerts",
            json={
                "title": f"DelAlert_{uid()}",
                "message": "To delete",
                "severity": "low",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            alert_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "DELETE",
                f"/api/v1/portal/admin/urgent-alerts/{alert_id}",
                headers=setup.admin_headers,
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminVetNetworkEndpoints:
    """Admin veterinary network endpoints."""

    async def test_create_vet_partner(self, client, setup):
        await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/veterinary-network",
            headers=setup.admin_headers,
            json={
                "name": f"VetPartner_{uid()}",
                "address": "Vet Partner St",
                "phone": "+1122334455",
            },
            expected=201,
        )

    async def test_update_vet_partner(self, client, setup):
        create_r = await client.post(
            "/api/v1/portal/admin/veterinary-network",
            json={
                "name": f"UpdPartner_{uid()}",
                "address": "Upd Partner St",
                "phone": "+1122334455",
            },
            headers=setup.admin_headers,
        )
        if create_r.status_code in (200, 201):
            partner_id = create_r.json()["data"]["id"]
            await call(
                client,
                "portal_admin",
                "PUT",
                f"/api/v1/portal/admin/veterinary-network/{partner_id}",
                headers=setup.admin_headers,
                json={
                    "phone": "+9988776655",
                },
                expected=200,
            )


@pytest.mark.asyncio
class TestPortalAdminSettingsEndpoints:
    """Admin portal settings endpoints."""

    async def test_get_admin_settings(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/settings",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_admin_setting(self, client, setup):
        await call(
            client,
            "portal_admin",
            "PUT",
            "/api/v1/portal/admin/settings/site_name",
            headers=setup.admin_headers,
            json={
                "value": "PawGuard Updated",
            },
            expected=200,
        )


@pytest.mark.asyncio
class TestPortalAdminCmsEndpoints:
    """Admin CMS page management endpoints."""

    async def test_get_cms_page(self, client, setup):
        await call(
            client,
            "portal_admin",
            "GET",
            "/api/v1/portal/admin/cms/pages/about",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_update_cms_page(self, client, setup):
        await call(
            client,
            "portal_admin",
            "PUT",
            "/api/v1/portal/admin/cms/pages/about",
            headers=setup.admin_headers,
            json={
                "title": "About Us",
                "content": "Updated about content",
            },
            expected=200,
        )

    async def test_publish_cms_page(self, client, setup):
        await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/cms/pages/about/publish",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_discard_cms_page(self, client, setup):
        await call(
            client,
            "portal_admin",
            "POST",
            "/api/v1/portal/admin/cms/pages/about/discard",
            headers=setup.admin_headers,
            expected=200,
        )

    async def test_public_cms_page(self, client):
        await call(client, "portal", "GET", "/api/v1/portal/cms/pages/about", expected=200)
