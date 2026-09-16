import asyncio
import uuid
from datetime import UTC, datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

DB_URL_RSL = "postgresql+asyncpg://postgres.rsllewhpzxpdstmjhmxj:PawGuard%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
DB_URL_GGZ = "postgresql+asyncpg://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"

STORAGE_BASE = "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media"

# Verified active images on Supabase rsllewhpzxpdstmjhmxj
IMG_MAYA = f"{STORAGE_BASE}/adoption%20images/pexels-kyoz-27732479.jpg"
IMG_DAISY = f"{STORAGE_BASE}/blog%20success%20stories/pexels-mohit-chanderh-129199578-18109070.jpg"
IMG_MAX = f"{STORAGE_BASE}/blog%20success%20stories/pexels-gustavodenuncio-26607813.jpg"
IMG_LUNA = f"{STORAGE_BASE}/blog%20success%20stories/pexels-humanistagram-12732006.jpg"
IMG_ROCKY = f"{STORAGE_BASE}/blog%20success%20stories/pexels-evlivanburak-10996406.jpg"
IMG_BRUNO = f"{STORAGE_BASE}/blog%20success%20stories/pexels-anny-patterson-2163004403-38626454.jpg"

STORIES_UPDATES = [
    {
        "id": "5703f709-cd8b-4e6e-bc55-de11ad5b1368",
        "title": "Maya Melody Story",
        "slug": "maya-melody-story",
        "summary": "Maya is very cute and loving pet who found her second chance through PawGuard's intensive care and dedicated foster network.",
        "body": "Maya was found near the busy Millbrook interchange suffering from severe trauma following a road incident. Our emergency ambulance team dispatched within 12 minutes, stabilizing her on-scene before transporting her to the trauma clinic.\n\nFollowing emergency surgery and 4 weeks of structured foster rehabilitation, Maya made a full recovery. She was formally adopted into a loving family home where she now enjoys beach runs and playing with her favorite tennis ball.",
        "hero_image_url": IMG_MAYA,
        "is_featured": True,
    },
    {
        "id": "ab325d36-9526-4f08-b8ff-09d8c5730a65",
        "title": "Daisy's Happy Tail",
        "slug": "daisys-happy-tail",
        "summary": "Found injured, Daisy recovered fully and was adopted by her rescue volunteer.",
        "body": "Daisy was found as a tiny puppy near a construction site, terrified of humans. Months of patient socialization at our shelter transformed her into a confident, affectionate young dog. Her rescue volunteer fell in love with her spirit and decided to officially welcome her into their family forever.",
        "hero_image_url": IMG_DAISY,
        "is_featured": False,
    },
    {
        "id": "faa5658c-79a4-4451-85b5-7b33a0e61a1e",
        "title": "Max's New Adventure",
        "slug": "maxs-new-adventure",
        "summary": "From a street rescue to a beloved family pet, Max's transformation is a testament to care and love.",
        "body": "Max was once a timid stray who flinched at raised voices. Through gentle desensitization, daily walks, and nutrition therapy, Max discovered his love for endurance running. Today he joins his adoptive family on weekly morning 10K jogs.",
        "hero_image_url": IMG_MAX,
        "is_featured": False,
    },
    {
        "id": "ea388158-0dc1-4007-86b6-52cc4c693e16",
        "title": "Luna Lights Up the Family",
        "slug": "luna-lights-up-the-family",
        "summary": "Luna, a sweet Indie pup, brought joy and companionship to a retired couple living in Jubilee Hills.",
        "body": "Luna was one of four puppies born at our shelter to a rescued mother. When the Iyer family visited looking for a companion, Luna picked them immediately. Today she is a cherished family member bringing endless laughter and comfort.",
        "hero_image_url": IMG_LUNA,
        "is_featured": False,
    },
    {
        "id": "dd760a81-fc3b-4aae-b040-b210512d2f65",
        "title": "Rocky's Second Chance",
        "slug": "rockys-second-chance",
        "summary": "Rocky found his perfect family after patience and care at PawGuard.",
        "body": "Rocky was brought to us with a severe spinal injury after being hit by a vehicle. Surgery and weeks of physiotherapy followed. Against all odds, he recovered and was placed with an experienced foster family who decided to adopt him permanently.",
        "hero_image_url": IMG_ROCKY,
        "is_featured": False,
    },
    {
        "id": "8e239d3f-6f79-4edc-8961-c26e7232f816",
        "title": "Bruno's Big Adventure: From Streets to Sofa",
        "slug": "brunos-big-adventure-from-streets-to-sofa",
        "summary": "Bruno spent two years in the shelter waiting for the right family. Today he has his own yard and best friend.",
        "body": "Bruno was first spotted limping near a busy intersection. Our rescue team reached him within the hour. After three months of medical care and behavioral training, Bruno found his forever home with a family who adore his gentle heart.",
        "hero_image_url": IMG_BRUNO,
        "is_featured": False,
    },
]

BLOGS_DATA = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "10 Essential Tips for First-Time Stray Dog Rescuers",
        "slug": "10-essential-tips-first-time-stray-dog-rescuers",
        "category": "Rescue Guides",
        "author": "PawGuard Rescue Team",
        "tags": "rescue, tips, emergency, stray",
        "excerpt": "Encountered an injured or scared stray dog? Here is our step-by-step guide to approaching, stabilizing, and reporting strays safely.",
        "body": "# 10 Essential Tips for First-Time Stray Dog Rescuers\n\nRescuing a stray dog in distress requires patience, calm composure, and safety precautions.",
        "cover_image_url": IMG_BRUNO,
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "title": "Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs",
        "slug": "understanding-canine-nutrition-shelter-dogs",
        "category": "Health & Nutrition",
        "author": "Dr. Priya Sharma, Senior Veterinarian",
        "tags": "nutrition, health, shelter, recovery",
        "excerpt": "How targeted high-protein diets and micronutrient supplementation help rescued dogs rebuild muscle mass and boost immunity.",
        "body": "# Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs\n\nWhen stray dogs arrive at our rescue shelter, malnutrition and gut dysbiosis are common.",
        "cover_image_url": IMG_MAYA,
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "title": "The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet",
        "slug": "the-3-3-3-rule-adopting-rescued-pet",
        "category": "Adoption Guides",
        "author": "Adoptions Desk",
        "tags": "adoption, training, care, family",
        "excerpt": "The first 3 days, 3 weeks, and 3 months with your new adopted dog are crucial for building lifelong trust.",
        "body": "# The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet\n\nBringing a rescue dog home is an exciting milestone.",
        "cover_image_url": IMG_ROCKY,
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "title": "Community Vaccination Drives: Eradicating Rabies One Sector at a Time",
        "slug": "community-vaccination-drives-eradicating-rabies",
        "category": "Community Initiatives",
        "author": "Field Operations Team",
        "tags": "vaccination, rabies, community, health",
        "excerpt": "PawGuard's annual mobile vaccination clinic vaccinated over 1,200 neighborhood strays this month.",
        "body": "# Community Vaccination Drives: Eradicating Rabies One Sector at a Time\n\nMass dog vaccination prevents rabies effectively.",
        "cover_image_url": IMG_LUNA,
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "title": "Senior Dogs: Why Older Canines Make the Most Loyal Companions",
        "slug": "senior-dogs-why-older-canines-make-loyal-companions",
        "category": "Adoption Guides",
        "author": "Welfare Council",
        "tags": "senior dogs, adoption, love, companions",
        "excerpt": "Senior dogs often get overlooked in shelters, yet they offer calm demeanor and unconditional affection.",
        "body": "# Senior Dogs: Why Older Canines Make the Most Loyal Companions\n\nSenior dogs possess a gentle wisdom.",
        "cover_image_url": IMG_MAX,
    },
    {
        "id": "66666666-6666-4666-8666-666666666666",
        "title": "Emergency First Aid for Injured Animals on the Road",
        "slug": "emergency-first-aid-injured-animals-road",
        "category": "Emergency Care",
        "author": "Emergency Dispatch",
        "tags": "first aid, emergency, trauma, rescue",
        "excerpt": "Crucial first-aid steps to stabilize trauma, control bleeding, and safely transport injured street dogs.",
        "body": "# Emergency First Aid for Injured Animals on the Road\n\nRoad traffic accidents are the leading emergency.",
        "cover_image_url": IMG_DAISY,
    },
]

async def sync_database(name: str, url: str):
    print(f"\n=======================================================")
    print(f"SYNCING STORIES & BLOG PHOTOS -> {name}")
    print("=======================================================")
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    now = datetime.now(UTC)

    async with engine.begin() as conn:
        # Delete old matching slugs/ids to avoid duplicate slug violations
        for s in STORIES_UPDATES:
            await conn.execute(
                text("DELETE FROM success_stories WHERE slug = :slug OR id = :id"),
                {"slug": s["slug"], "id": uuid.UUID(s["id"])}
            )
        for b in BLOGS_DATA:
            await conn.execute(
                text("DELETE FROM blog_posts WHERE slug = :slug OR id = :id"),
                {"slug": b["slug"], "id": uuid.UUID(b["id"])}
            )

        # 1. Insert the 6 primary stories
        for s in STORIES_UPDATES:
            story_uuid = uuid.UUID(s["id"])
            await conn.execute(
                text("""
                    INSERT INTO success_stories (id, title, slug, summary, body, hero_image_url, status, is_featured, has_consent, sort_order, published_at, created_at, updated_at)
                    VALUES (:id, :title, :slug, :summary, :body, :hero_image_url, 'published', :is_featured, true, 0, :published_at, :created_at, :updated_at)
                """),
                {
                    "id": story_uuid,
                    "title": s["title"],
                    "slug": s["slug"],
                    "summary": s["summary"],
                    "body": s["body"],
                    "hero_image_url": s["hero_image_url"],
                    "is_featured": s["is_featured"],
                    "published_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            print(f"  [SAVED STORY] {s['title']} ({story_uuid}) -> {s['hero_image_url']}")

        # 2. Fix all other remaining stories with dead/relative images
        await conn.execute(
            text(f"""
                UPDATE success_stories
                SET hero_image_url = '{IMG_MAX}'
                WHERE hero_image_url IS NULL 
                   OR hero_image_url NOT LIKE 'http%'
                   OR hero_image_url LIKE '%xzxsdgobndbkufyszzul%'
                   OR hero_image_url LIKE '%ggzguyqptcedoudfkiev%'
            """)
        )

        # 3. Insert Blog Posts
        for b in BLOGS_DATA:
            blog_uuid = uuid.UUID(b["id"])
            await conn.execute(
                text("""
                    INSERT INTO blog_posts (id, title, slug, category, author, tags, excerpt, body, cover_image_url, status, published_at, created_at, updated_at)
                    VALUES (:id, :title, :slug, :category, :author, :tags, :excerpt, :body, :cover_image_url, 'published', :published_at, :created_at, :updated_at)
                """),
                {
                    "id": blog_uuid,
                    "title": b["title"],
                    "slug": b["slug"],
                    "category": b["category"],
                    "author": b["author"],
                    "tags": b["tags"],
                    "excerpt": b["excerpt"],
                    "body": b["body"],
                    "cover_image_url": b["cover_image_url"],
                    "published_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            print(f"  [SAVED BLOG] {b['title']} -> {b['cover_image_url']}")

        # 4. Fix any remaining blog posts with broken image URLs
        await conn.execute(
            text(f"""
                UPDATE blog_posts
                SET cover_image_url = '{IMG_MAYA}'
                WHERE cover_image_url IS NULL 
                   OR cover_image_url NOT LIKE 'http%'
                   OR cover_image_url LIKE '%xzxsdgobndbkufyszzul%'
                   OR cover_image_url LIKE '%ggzguyqptcedoudfkiev%'
            """)
        )

    await engine.dispose()
    print(f"\n[DONE] Finished syncing {name} successfully!")

async def main():
    await sync_database("RSL (User's Active Production Supabase)", DB_URL_RSL)
    await sync_database("GGZ (Staging Supabase)", DB_URL_GGZ)

if __name__ == "__main__":
    asyncio.run(main())
