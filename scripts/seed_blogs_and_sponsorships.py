"""Seed mock Blog Posts and Dog Sponsorships for the PawGuard ecosystem.

Usage:
    uv run python scripts/seed_blogs_and_sponsorships.py
"""

import asyncio
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from pawguard.core.config import get_settings
from pawguard.modules.auth.models import User
from pawguard.modules.dog.models import DogProfile
from pawguard.modules.donation.models import DogSponsorship, DonorProfile, SponsorshipStatus
from pawguard.modules.portal.models import BlogPost, ContentStatus

MOCK_BLOG_POSTS = [
    {
        "title": "10 Essential Tips for First-Time Stray Dog Rescuers",
        "slug": "10-essential-tips-first-time-stray-dog-rescuers",
        "category": "Rescue Guides",
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
        "title": "Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs",
        "slug": "understanding-canine-nutrition-shelter-dogs",
        "category": "Health & Nutrition",
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
        "title": "The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet",
        "slug": "the-3-3-3-rule-adopting-rescued-pet",
        "category": "Adoption Guides",
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
        "title": "Community Vaccination Drives: Eradicating Rabies One Sector at a Time",
        "slug": "community-vaccination-drives-eradicating-rabies",
        "category": "Community Initiatives",
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
        "title": "Senior Dogs: Why Older Canines Make the Most Loyal Companions",
        "slug": "senior-dogs-why-older-canines-make-loyal-companions",
        "category": "Adoption Guides",
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
]


async def seed_blogs_and_sponsorships(label: str, database_url: str) -> None:
    if not database_url:
        print(f"SKIP [{label}]: No database URL configured.")
        return

    print("\n=======================================================")
    print(f"SEEDING [{label}] -> Blogs & Dog Sponsorships")
    print("=======================================================")

    engine = create_async_engine(database_url, echo=False, connect_args={"statement_cache_size": 0})
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    now = datetime.now(UTC)
    today = date.today()

    async with session_factory() as session:
        # ── 1. Seed Blog Posts ───────────────────────────────────────────────
        blog_count = 0
        for bp_data in MOCK_BLOG_POSTS:
            existing = (
                (await session.execute(select(BlogPost).where(BlogPost.slug == bp_data["slug"])))
                .scalars()
                .first()
            )

            if existing is None:
                post = BlogPost(
                    id=uuid.uuid4(),
                    title=bp_data["title"],
                    slug=bp_data["slug"],
                    category=bp_data["category"],
                    excerpt=bp_data["excerpt"],
                    body=bp_data["body"],
                    cover_image_url=bp_data["cover_image_url"],
                    status=bp_data["status"],
                    published_at=now,
                )
                session.add(post)
                blog_count += 1
                print(f"  [+] Added Blog: '{bp_data['title']}' ({bp_data['category']})")
            else:
                print(f"  [.] Blog exists: '{bp_data['slug']}'")

        await session.flush()
        print(f"--> Total new blog posts added: {blog_count}")

        # ── 2. Seed Donor Profiles & Dog Sponsorships ─────────────────────────
        users = (await session.execute(select(User))).scalars().all()
        dogs = (await session.execute(select(DogProfile))).scalars().all()

        if not users:
            print("  [!] No users found in database to create sponsorships.")
        elif not dogs:
            print("  [!] No dogs found in database to sponsor.")
        else:
            # Create donor profiles for available users
            donor_profiles = []
            for idx, user in enumerate(users[:5]):
                profile = (
                    (
                        await session.execute(
                            select(DonorProfile).where(DonorProfile.user_id == user.id)
                        )
                    )
                    .scalars()
                    .first()
                )

                if profile is None:
                    profile = DonorProfile(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        tax_identifier=f"80G-PAN-PG{idx + 101}X",
                        notes=f"Tier {idx + 1} Sustaining Animal Welfare Patron",
                    )
                    session.add(profile)
                    await session.flush()
                    print(f"  [+] Created DonorProfile for user {user.email}")
                donor_profiles.append(profile)

            # Create Dog Sponsorships
            amounts = [25.0, 50.0, 75.0, 100.0, 150.0]
            sponsorship_count = 0

            for i, dog in enumerate(dogs):
                donor = donor_profiles[i % len(donor_profiles)]
                existing_sp = (
                    (
                        await session.execute(
                            select(DogSponsorship).where(
                                DogSponsorship.dog_id == dog.id,
                                DogSponsorship.donor_id == donor.id,
                            )
                        )
                    )
                    .scalars()
                    .first()
                )

                if existing_sp is None:
                    monthly_amt = amounts[i % len(amounts)]
                    sp = DogSponsorship(
                        id=uuid.uuid4(),
                        donor_id=donor.id,
                        dog_id=dog.id,
                        monthly_amount=monthly_amt,
                        currency="USD",
                        status=SponsorshipStatus.ACTIVE,
                        started_at=now - timedelta(days=15 * (i + 1)),
                        next_charge_date=today + timedelta(days=30),
                    )
                    session.add(sp)
                    sponsorship_count += 1
                    print(
                        f"  [+] Sponsored Dog '{dog.name}' by Donor {donor.id} (${monthly_amt}/mo)"
                    )

            print(f"--> Total new dog sponsorships added: {sponsorship_count}")

        await session.commit()
        print(f"\n[OK] Successfully completed seeding for [{label}].\n")

    await engine.dispose()


async def main() -> None:
    settings = get_settings()
    await seed_blogs_and_sponsorships("Backend Primary DB", settings.database_url)
    if settings.database_url_frontend:
        await seed_blogs_and_sponsorships("Frontend Secondary DB", settings.database_url_frontend)


if __name__ == "__main__":
    asyncio.run(main())
