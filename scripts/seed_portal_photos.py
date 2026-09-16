import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.portal.models import ContentStatus

BLOG_POSTS_DATA = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "10 Essential Tips for First-Time Stray Dog Rescuers",
        "slug": "10-essential-tips-first-time-stray-dog-rescuers",
        "category": "Rescue Guides",
        "author": "PawGuard Rescue Team",
        "tags": "rescue, tips, emergency, stray",
        "excerpt": "Encountered an injured or scared stray dog? Here is our step-by-step guide to approaching, stabilizing, and reporting strays safely.",
        "body": """# 10 Essential Tips for First-Time Stray Dog Rescuers

Rescuing a stray dog in distress requires patience, calm composure, and safety precautions. Whether you encounter a malnourished puppy or an injured street dog, follow these ten critical guidelines:

### 1. Prioritize Your Own Safety First
Never corner a distressed animal. An injured or frightened dog may bite out of fear or defense. Always evaluate the surrounding traffic and environment before approaching.

### 2. Observe Body Language
Look for warning signs such as pinned-back ears, growling, stiff body posture, or whale eye (showing the whites of their eyes). A submissive dog may tuck its tail or cower.

### 3. Use Food as a Gentle Enticement
Strong-smelling treats (like boiled chicken or soft treats) can help build immediate trust. Toss treats gently towards the dog without making sudden forward movements.

### 4. Avoid Direct Eye Contact and Looming
Direct eye contact can be perceived as an aggressive challenge. Keep your body turned slightly sideways and crouch down to appear less intimidating.

### 5. Have a Slip Lead Ready
A slip lead is far safer and quicker to loop over a stray dog's head than trying to buckle a collar.

### 6. Create a Warm, Secure Holding Area
If transporting in a vehicle, line the seat or crate with clean towels or blankets to keep the animal warm and contain any dirt or fluids.

### 7. Never Force Food or Water on an Injured Dog
If the dog has internal injuries or might need immediate surgery under anesthesia, feeding them could cause severe complications or aspiration.

### 8. Document Location and Distinctive Markings
Take clear photos and note exact GPS coordinates. This is vital for cross-referencing lost pet databases in PawGuard.

### 9. Report via the PawGuard Emergency Dispatch
Submit a rescue incident through the PawGuard mobile app or portal. Our rapid dispatch coordinators assign nearby ambulance fleets immediately.

### 10. Follow Up on Veterinary Clearance
Ensure the rescued canine receives a full veterinary triage, rabies vaccination, and antiparasitic treatment before transitioning to shelter or foster care.
""",
        "cover_image_url": "https://images.unsplash.com/photo-1548199973-03cce0bbc87b?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "title": "Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs",
        "slug": "understanding-canine-nutrition-shelter-dogs",
        "category": "Health & Nutrition",
        "author": "Dr. Priya Sharma, Senior Veterinarian",
        "tags": "nutrition, health, shelter, recovery",
        "excerpt": "How targeted high-protein diets and micronutrient supplementation help rescued dogs rebuild muscle mass and boost immunity.",
        "body": """# Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs

When stray dogs arrive at our rescue shelter, malnutrition and gut dysbiosis are among the most frequent clinical diagnoses. Restoring a rescued dog's vitality requires a carefully phased nutritional strategy.

### The Dangers of Refeeding Syndrome
Starving dogs cannot simply be offered large bowls of rich kibble. Rapid refeeding can trigger dangerous electrolyte shifts (hypophosphatemia and hypokalemia) that stress the cardiovascular system.

### Phased Nutritional Rehabilitation
1. **Phase 1 (Days 1–3):** Small, frequent meals consisting of easily digestible proteins (boiled poultry, bone broth, and pumpkin puree) fed 4–6 times daily.
2. **Phase 2 (Days 4–10):** Transition to veterinary-formulated gastrointestinal recovery wet diets enriched with zinc, omega-3 fatty acids, and B-complex vitamins.
3. **Phase 3 (Day 11 onwards):** Gradual introduction of high-protein age-appropriate adult kibble, probiotic flora support, and joint supplements for larger breeds.

### Monitoring Body Condition Score (BCS)
Our veterinary suite tracks BCS metrics weekly on a 1-to-9 scale, aiming for a healthy 4 to 5 range before clearing dogs for foster or adoption.
""",
        "cover_image_url": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "title": "The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet",
        "slug": "the-3-3-3-rule-adopting-rescued-pet",
        "category": "Adoption Guides",
        "author": "Adoptions Desk",
        "tags": "adoption, training, care, family",
        "excerpt": "The first 3 days, 3 weeks, and 3 months with your new adopted dog are crucial for building lifelong trust. Here is what to expect.",
        "body": """# The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet

Bringing a rescue dog home is an exciting milestone, but transition shock is completely natural. The **3-3-3 Rule** is a general guideline to understand the psychological phases your new pet experiences:

---

### In the First 3 Days: Decompression
- The dog feels overwhelmed, scared, or shut down.
- May not eat or drink much initially.
- May test boundaries or hide under furniture.
- **Tip:** Keep things calm and low-key. Avoid inviting large groups of guests or visiting dog parks.

---

### In the First 3 Weeks: Settling In
- The dog begins to feel comfortable and recognizes their routine.
- True personality traits start to surface.
- May exhibit minor behavioral quirks that require positive reinforcement.
- **Tip:** Maintain strict consistency with feeding schedules, walk times, and house-training routines.

---

### In the First 3 Months: Building Complete Trust
- The dog feels entirely at home and bonded to the family.
- Builds a sense of security and loyalty with their caregivers.
- Ready for advanced training, agility, or social interactions.
- **Tip:** Continue positive praise, gentle training, and routine veterinary wellness check-ups.
""",
        "cover_image_url": "https://images.unsplash.com/photo-1537151625747-768eb6cf92b2?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "title": "Community Vaccination Drives: Eradicating Rabies One Sector at a Time",
        "slug": "community-vaccination-drives-eradicating-rabies",
        "category": "Community Initiatives",
        "author": "Field Operations Team",
        "tags": "vaccination, rabies, community, health",
        "excerpt": "PawGuard's annual mobile vaccination clinic vaccinated over 1,200 neighborhood strays this month. Read the impact report.",
        "body": """# Community Vaccination Drives: Eradicating Rabies One Sector at a Time

Mass dog vaccination is the single most cost-effective and humane strategy for preventing rabies in both humans and animals. This month, PawGuard's mobile veterinary team deployed across high-density urban clusters.

### Key Milestones Achieved:
- **1,240 Strays Vaccinated:** Anti-rabies (ARV) and 9-in-1 DHPPiL vaccinations administered.
- **Smart QR Tag Collars Fitted:** Over 850 community strays fitted with durable, reflective QR-linked collars.
- **Microchip Registry Integration:** Digital IDs synced in real-time with the municipal welfare portal.

Join our upcoming volunteer weekend to help census and collar strays in your residential block!
""",
        "cover_image_url": "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "title": "Senior Dogs: Why Older Canines Make the Most Loyal Companions",
        "slug": "senior-dogs-why-older-canines-make-loyal-companions",
        "category": "Adoption Guides",
        "author": "Welfare Council",
        "tags": "senior dogs, adoption, love, companions",
        "excerpt": "Senior dogs often get overlooked in shelters, yet they offer calm demeanor, established house training, and unconditional affection.",
        "body": """# Senior Dogs: Why Older Canines Make the Most Loyal Companions

While puppies attract immediate attention, senior dogs (ages 7 and older) possess a gentle wisdom and quiet companionship that is unmatched.

### Why Adopt a Senior Dog?
1. **Established Manners:** Most older dogs are already house-trained and know basic commands.
2. **Lower Energy Requirements:** A leisurely stroll around the block and cozy couch naps are often all they need.
3. **What You See Is What You Get:** Their full-grown size, coat, and personality are fully established.
4. **Immediate Gratitude:** Rescued senior dogs seem to possess an innate understanding that they have been given a second chance at happiness.

Consider opening your home to a senior shelter resident today!
""",
        "cover_image_url": "https://images.unsplash.com/photo-1518717758536-85ae29035b6d?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "66666666-6666-4666-8666-666666666666",
        "title": "Emergency First Aid for Injured Animals on the Road",
        "slug": "emergency-first-aid-injured-animals-road",
        "category": "Emergency Care",
        "author": "Emergency Dispatch",
        "tags": "first aid, emergency, trauma, rescue",
        "excerpt": "Crucial first-aid steps to stabilize trauma, control bleeding, and safely transport injured street dogs to nearest clinics.",
        "body": """# Emergency First Aid for Injured Animals on the Road

Road traffic accidents are the leading cause of emergency calls received at the PawGuard dispatch center. Knowing how to administer rapid on-scene triage can save an animal's life.

### Critical Action Protocol:
1. **Secure the Scene:** Park with hazard lights on to create a physical barrier against oncoming traffic.
2. **Handle with Care:** Use a thick blanket or jacket to gently lift the animal, supporting both the chest and pelvis.
3. **Control Hemorrhage:** Apply direct pressure with a clean sterile gauze or cloth to bleeding sites. Avoid tourniquets unless trained.
4. **Prevent Hypothermia:** Wrap the animal snugly to maintain core body temperature during transport.
5. **Call Hotline:** Dial the 24/7 PawGuard emergency hotline (+91 98765 43210) for in-route doctor prep.
""",
        "cover_image_url": "https://images.unsplash.com/photo-1587300003388-59208cc962cb?auto=format&fit=crop&w=1200&q=80",
        "status": ContentStatus.PUBLISHED,
    },
]

SUCCESS_STORIES_DATA = [
    {
        "id": "5703f709-cd8b-4e6e-bc55-de11ad5b1368",
        "title": "Maya Melody Story",
        "slug": "maya-melody-story",
        "summary": "Maya is very cute and loving pet who found her second chance through PawGuard's intensive care and dedicated foster network.",
        "body": """Maya was found near the busy Millbrook interchange suffering from severe trauma following a road incident. Our emergency ambulance team dispatched within 12 minutes, stabilizing her on-scene before transporting her to the trauma clinic.

Following emergency surgery and 4 weeks of structured foster rehabilitation, Maya made a full recovery. She was formally adopted into a loving family home where she now enjoys beach runs and playing with her favorite tennis ball.
""",
        "hero_image_url": "https://images.unsplash.com/photo-1601758228041-f3b2795255f1?w=800&h=500&fit=crop&auto=format",
        "is_featured": True,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "ab325d36-9526-4f08-b8ff-09d8c5730a65",
        "title": "Daisy's Happy Tail",
        "slug": "daisys-happy-tail",
        "summary": "Found injured, Daisy recovered fully and was adopted by her rescue volunteer.",
        "body": """Daisy was found as a tiny puppy near a construction site, terrified of humans. Months of patient socialization at our shelter transformed her into a confident, affectionate young dog. Her rescue volunteer fell in love with her spirit and decided to officially welcome her into their family forever.""",
        "hero_image_url": "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?w=800&h=500&fit=crop&auto=format",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "faa5658c-79a4-4451-85b5-7b33a0e61a1e",
        "title": "Max's New Adventure",
        "slug": "maxs-new-adventure",
        "summary": "From a street rescue to a beloved family pet, Max's transformation is a testament to care and love.",
        "body": """Max was once a timid stray who flinched at raised voices. Through gentle desensitization, daily walks, and nutrition therapy, Max discovered his love for endurance running. Today he joins his adoptive family on weekly morning 10K jogs.""",
        "hero_image_url": "https://images.unsplash.com/photo-1552053831-71594a27632d?w=800&h=500&fit=crop&auto=format",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "ea388158-0dc1-4007-86b6-52cc4c693e16",
        "title": "Luna Lights Up the Family",
        "slug": "luna-lights-up-the-family",
        "summary": "Luna, a sweet Indie pup, brought joy and companionship to a retired couple living in Jubilee Hills.",
        "body": """Luna was one of four puppies born at our shelter to a rescued mother. When the Iyer family visited looking for a companion, Luna picked them immediately. Today she is a cherished family member bringing endless laughter and comfort.""",
        "hero_image_url": "https://images.unsplash.com/photo-1518717758536-85ae29035b6d?w=800&h=500&fit=crop&auto=format",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "dd760a81-fc3b-4aae-b040-b210512d2f65",
        "title": "Rocky's Second Chance",
        "slug": "rockys-second-chance",
        "summary": "Rocky found his perfect family after patience and care at PawGuard.",
        "body": """Rocky was brought to us with a severe spinal injury after being hit by a vehicle. Surgery and weeks of physiotherapy followed. Against all odds, he recovered and was placed with an experienced foster family who decided to adopt him permanently.""",
        "hero_image_url": "https://images.unsplash.com/photo-1561037404-61cd46aa615b?w=800&h=500&fit=crop&auto=format",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "id": "8e239d3f-6f79-4edc-8961-c26e7232f816",
        "title": "Bruno's Big Adventure: From Streets to Sofa",
        "slug": "brunos-big-adventure-from-streets-to-sofa",
        "summary": "Bruno spent months in the shelter waiting for the right family. Today he has his own yard and best friend.",
        "body": """Bruno was first spotted limping near a busy intersection. Our rescue team reached him within the hour. After three months of medical care and behavioral training, Bruno found his forever home with a family who adore his gentle heart.""",
        "hero_image_url": "https://images.unsplash.com/photo-1537151608828-ea2b11777ee8?w=800&h=500&fit=crop&auto=format",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
]


async def seed_database(label: str, db_url: str):
    if not db_url:
        return
    print(f"\nSeeding database [{label}] ...")
    engine = create_async_engine(db_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with session_factory() as session:
        # 1. Clean old entries
        for s in SUCCESS_STORIES_DATA:
            await session.execute(
                text("DELETE FROM success_stories WHERE slug = :slug OR id = :id"),
                {"slug": s["slug"], "id": uuid.UUID(s["id"])}
            )
        for b in BLOG_POSTS_DATA:
            await session.execute(
                text("DELETE FROM blog_posts WHERE slug = :slug OR id = :id"),
                {"slug": b["slug"], "id": uuid.UUID(b["id"])}
            )

        # 2. Insert Blog Posts with photos
        print("--- Seeding Blog Posts with Photos ---")
        for b in BLOG_POSTS_DATA:
            await session.execute(
                text("""
                    INSERT INTO blog_posts (id, title, slug, category, author, tags, excerpt, body, cover_image_url, status, published_at, created_at, updated_at)
                    VALUES (:id, :title, :slug, :category, :author, :tags, :excerpt, :body, :cover_image_url, :status, :published_at, :created_at, :updated_at)
                """),
                {
                    "id": uuid.UUID(b["id"]),
                    "title": b["title"],
                    "slug": b["slug"],
                    "category": b["category"],
                    "author": b.get("author"),
                    "tags": b.get("tags"),
                    "excerpt": b["excerpt"],
                    "body": b["body"],
                    "cover_image_url": b["cover_image_url"],
                    "status": b["status"].value if hasattr(b["status"], "value") else b["status"],
                    "published_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            print(f"  [INSERTED] Blog: {b['title']} -> Image: {b['cover_image_url']}")

        # 3. Insert Success Stories matching frontend UUIDs
        print("\n--- Seeding Success Stories with Photos ---")
        for s in SUCCESS_STORIES_DATA:
            target_uuid = uuid.UUID(s["id"])
            await session.execute(
                text("""
                    INSERT INTO success_stories (id, title, slug, summary, body, hero_image_url, status, is_featured, has_consent, sort_order, published_at, created_at, updated_at)
                    VALUES (:id, :title, :slug, :summary, :body, :hero_image_url, :status, :is_featured, true, 0, :published_at, :created_at, :updated_at)
                """),
                {
                    "id": target_uuid,
                    "title": s["title"],
                    "slug": s["slug"],
                    "summary": s["summary"],
                    "body": s["body"],
                    "hero_image_url": s["hero_image_url"],
                    "status": s["status"].value if hasattr(s["status"], "value") else s["status"],
                    "is_featured": s["is_featured"],
                    "published_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            print(f"  [INSERTED] Story: {s['title']} ({target_uuid}) -> Image: {s['hero_image_url']}")

        # Clear any remaining stories with broken non-http URLs
        await session.execute(
            text("""
                UPDATE success_stories 
                SET hero_image_url = 'https://images.unsplash.com/photo-1548199973-03cce0bbc87b?auto=format&fit=crop&w=1200&q=80'
                WHERE hero_image_url NOT LIKE 'http%'
            """)
        )

        await session.commit()
        print(f"\n[SUCCESS] Successfully committed all blog posts and success stories for [{label}]!")

    await engine.dispose()


async def main():
    settings = get_settings()
    await seed_database("Primary DB", settings.database_url)
    if settings.database_url_frontend and settings.database_url_frontend != settings.database_url:
        await seed_database("Frontend DB", settings.database_url_frontend)


if __name__ == "__main__":
    asyncio.run(main())
