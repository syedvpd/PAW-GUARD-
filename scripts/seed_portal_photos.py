import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.portal.models import BlogPost, ContentStatus, SuccessStory

BLOG_POSTS_DATA = [
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-anny-patterson-2163004403-38626454.jpg",
        "status": ContentStatus.PUBLISHED,
    },
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/adoption%20images/pexels-kyoz-27732479.jpg",
        "status": ContentStatus.PUBLISHED,
    },
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-evlivanburak-10996406.jpg",
        "status": ContentStatus.PUBLISHED,
    },
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-humanistagram-12732006.jpg",
        "status": ContentStatus.PUBLISHED,
    },
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-gustavodenuncio-26607813.jpg",
        "status": ContentStatus.PUBLISHED,
    },
    {
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
        "cover_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-mohit-chanderh-129199578-18109070.jpg",
        "status": ContentStatus.PUBLISHED,
    }
]

SUCCESS_STORIES_DATA = [
    {
        "title": "Maya Melody Story",
        "slug": "maya-melody-story",
        "summary": "Maya is very cute and loving pet who found her second chance through PawGuard's intensive care and dedicated foster network.",
        "body": """Maya was found near the busy Millbrook interchange suffering from severe trauma following a road incident. Our emergency ambulance team dispatched within 12 minutes, stabilizing her on-scene before transporting her to the trauma clinic.

Following emergency surgery and 4 weeks of structured foster rehabilitation, Maya made a full recovery. She was formally adopted into a loving family home where she now enjoys beach runs and playing with her favorite tennis ball.
""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/adoption%20images/pexels-kyoz-27732479.jpg",
        "is_featured": True,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "title": "Daisy's Happy Tail",
        "slug": "daisys-happy-tail",
        "summary": "Found injured, Daisy recovered fully and was adopted by her rescue volunteer.",
        "body": """Daisy was found as a tiny puppy near a construction site, terrified of humans. Months of patient socialization at our shelter transformed her into a confident, affectionate young dog. Her rescue volunteer fell in love with her spirit and decided to officially welcome her into their family forever.""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-mohit-chanderh-129199578-18109070.jpg",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "title": "Max's New Adventure",
        "slug": "maxs-new-adventure",
        "summary": "From a street rescue to a beloved family pet, Max's transformation is a testament to care and love.",
        "body": """Max was once a timid stray who flinched at raised voices. Through gentle desensitization, daily walks, and nutrition therapy, Max discovered his love for endurance running. Today he joins his adoptive family on weekly morning 10K jogs.""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-gustavodenuncio-26607813.jpg",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "title": "Luna Lights Up the Family",
        "slug": "luna-lights-up-the-family",
        "summary": "Luna, a sweet Indie pup, brought joy and companionship to a retired couple living in Jubilee Hills.",
        "body": """Luna was one of four puppies born at our shelter to a rescued mother. When the Iyer family visited looking for a companion, Luna picked them immediately. Today she is a cherished family member bringing endless laughter and comfort.""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-humanistagram-12732006.jpg",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "title": "Rocky's Second Chance",
        "slug": "rockys-second-chance",
        "summary": "Rocky found his perfect family after patience and care at PawGuard.",
        "body": """Rocky was brought to us with a severe spinal injury after being hit by a vehicle. Surgery and weeks of physiotherapy followed. Against all odds, he recovered and was placed with an experienced foster family who decided to adopt him permanently.""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-evlivanburak-10996406.jpg",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    },
    {
        "title": "Bruno's Big Adventure: From Streets to Sofa",
        "slug": "brunos-big-adventure-from-streets-to-sofa",
        "summary": "Bruno spent months in the shelter waiting for the right family. Today he has his own yard and best friend.",
        "body": """Bruno was first spotted limping near a busy intersection. Our rescue team reached him within the hour. After three months of medical care and behavioral training, Bruno found his forever home with a family who adore his gentle heart.""",
        "hero_image_url": "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-anny-patterson-2163004403-38626454.jpg",
        "is_featured": False,
        "status": ContentStatus.PUBLISHED,
    }
]


async def seed_media_and_content():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)

    async with session_factory() as session:
        # 1. Seed or Update Blog Posts with photos
        print("--- Seeding / Updating Blog Posts with S3/Supabase Photos ---")
        for b in BLOG_POSTS_DATA:
            existing = (await session.execute(select(BlogPost).where(BlogPost.slug == b["slug"]))).scalars().first()
            if existing:
                existing.title = b["title"]
                existing.category = b["category"]
                existing.excerpt = b["excerpt"]
                existing.body = b["body"]
                existing.cover_image_url = b["cover_image_url"]
                existing.status = b["status"]
                existing.author = b.get("author")
                existing.tags = b.get("tags")
                if not existing.published_at:
                    existing.published_at = now
                print(f"  [UPDATED] Blog: {b['slug']} -> Image: {b['cover_image_url']}")
            else:
                new_post = BlogPost(
                    id=uuid.uuid4(),
                    title=b["title"],
                    slug=b["slug"],
                    category=b["category"],
                    author=b.get("author"),
                    tags=b.get("tags"),
                    excerpt=b["excerpt"],
                    body=b["body"],
                    cover_image_url=b["cover_image_url"],
                    status=b["status"],
                    published_at=now,
                )
                session.add(new_post)
                print(f"  [CREATED] Blog: {b['slug']} -> Image: {b['cover_image_url']}")

        # 2. Seed or Update Success Stories with photos
        print("\n--- Seeding / Updating Success Stories with S3/Supabase Photos ---")
        for s in SUCCESS_STORIES_DATA:
            existing = (await session.execute(select(SuccessStory).where(
                (SuccessStory.slug == s["slug"]) | (SuccessStory.title == s["title"])
            ))).scalars().first()
            if existing:
                existing.title = s["title"]
                existing.slug = s["slug"]
                existing.summary = s["summary"]
                existing.body = s["body"]
                existing.hero_image_url = s["hero_image_url"]
                existing.status = s["status"]
                existing.is_featured = s["is_featured"]
                if not existing.published_at:
                    existing.published_at = now
                print(f"  [UPDATED] Story: {s['title']} -> Image: {s['hero_image_url']}")
            else:
                new_story = SuccessStory(
                    id=uuid.uuid4(),
                    title=s["title"],
                    slug=s["slug"],
                    summary=s["summary"],
                    body=s["body"],
                    hero_image_url=s["hero_image_url"],
                    status=s["status"],
                    is_featured=s["is_featured"],
                    has_consent=True,
                    published_at=now,
                )
                session.add(new_story)
                print(f"  [CREATED] Story: {s['title']} -> Image: {s['hero_image_url']}")

        await session.commit()
        print("\n[SUCCESS] Successfully committed all blog posts and success stories with photos!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_media_and_content())
