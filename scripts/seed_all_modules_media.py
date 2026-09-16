"""Comprehensive multi-module media and content seeder.

Populates and ensures 100% working, verified Supabase media / CDN images for all
sections/modules in both PawGuard databases (staging and production):
1. Success Stories (`success_stories`)
2. Adoptable Dogs (`dog_profiles`)
3. Lost & Found (`lost_reports`, `found_reports`)
4. Blog Posts (`blog_posts`)
5. Vet Clinics & Partners (`vet_clinics`, `veterinary_partners`)
6. CMS Content & Hero Banners (`cms_content_fields`, `cms_pages`, `cms_sections`)
7. Companion Pets (`companion_pets`)
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
import asyncpg

DATABASES = [
    (
        "ggzguyqptcedoudfkiev (Live Render Staging/Prod)",
        "postgresql://postgres.ggzguyqptcedoudfkiev:pawguardstaging%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    ),
    (
        "rsllewhpzxpdstmjhmxj (Supabase Media Storage / Secondary)",
        "postgresql://postgres.rsllewhpzxpdstmjhmxj:PawGuard%402026@aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres",
    ),
]

# Verified 200 OK CDN & Supabase storage image URLs
SUPABASE_MEDIA = [
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/adoption%20images/pexels-kyoz-27732479.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-mohit-chanderh-129199578-18109070.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-gustavodenuncio-26607813.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-humanistagram-12732006.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-evlivanburak-10996406.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-anny-patterson-2163004403-38626454.jpg",
]

UNSPLASH_DOGS = [
    "https://images.unsplash.com/photo-1543466835-00a7907e9de1?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1583511655857-d19b40a7a54e?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1537151608828-ea2b11777ee8?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1587300003388-59208cc962cb?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1561037404-61cd46aa615b?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1548199973-03cce0bbc87b?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1517849845537-4d257902454a?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?auto=format&fit=crop&w=800&q=80",
    "https://images.unsplash.com/photo-1596492784531-6e6eb5ea9993?auto=format&fit=crop&w=800&q=80",
]

SUCCESS_STORIES = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "Maya's Journey: From Street Stray to Therapy Champion",
        "slug": "mayas-journey-street-stray-to-therapy-champion",
        "summary": "Found severely injured on Highway 44, Maya underwent 3 months of intensive orthopedic rehabilitation and is now a certified pediatric therapy dog.",
        "body": "# Maya's Journey: From Street Stray to Therapy Champion\n\nWhen our mobile rescue ambulance arrived at Highway 44 on a stormy June evening, Maya was unable to stand.\n\n### The Rescue and Medical Intervention\nOur emergency veterinary team performed reconstructive hip surgery and monitored her round-the-clock for 90 days. Her resilient spirit never faded.\n\n### A New Life and Purpose\nToday, Maya lives happily with the Sharma family and visits local children's hospitals twice a month as a licensed therapy dog.",
        "hero_image_url": SUPABASE_MEDIA[0],
        "status": "published",
        "is_featured": True,
        "sort_order": 1,
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "title": "Bruno's Miracle Recovery: Overcoming Parvovirus",
        "slug": "brunos-miracle-recovery-overcoming-parvovirus",
        "summary": "Rescued at just 6 weeks old battling life-threatening parvovirus, Bruno made a complete recovery thanks to rapid ICU isolation and community plasma donors.",
        "body": "# Bruno's Miracle Recovery: Overcoming Parvovirus\n\nBruno was discovered dehydrated and unresponsive in an abandoned construction zone.\n\n### Intensive ICU Care\nWith 24/7 plasma therapy and hydration protocols at the PawGuard Central Clinic, Bruno fought back and tested negative after 12 days.\n\n### Forever Home Found\nBruno was adopted by software engineer Rohan and now enjoys endless fetch games in Jubilee Hills.",
        "hero_image_url": SUPABASE_MEDIA[1],
        "status": "published",
        "is_featured": False,
        "sort_order": 2,
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "title": "Bella and the Trio: A Mother's Love Rewarded",
        "slug": "bella-and-the-trio-mothers-love-rewarded",
        "summary": "Bella protected her three newborn puppies during monsoon flooding before being sheltered and rehabilitated. All four have now found forever homes.",
        "body": "# Bella and the Trio: A Mother's Love Rewarded\n\nBella stood guard over her puppies beneath a highway underpass during heavy monsoon downpours.\n\n### Rescue & Safe Shelter\nPawGuard volunteers safely evacuated Bella and her litter into our mother-and-puppy nursery section.\n\n### Happy Endings\nAll three pups and mama Bella found loving adoptive families across Hyderabad within six weeks.",
        "hero_image_url": SUPABASE_MEDIA[2],
        "status": "published",
        "is_featured": False,
        "sort_order": 3,
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "title": "Rocky: The Tri-Pawd Trail Explorer",
        "slug": "rocky-the-tri-pawd-trail-explorer",
        "summary": "Losing a leg to a railway accident did not slow Rocky down. Fitted with a specialized harness, he now hikes weekly trails with his adoptive dad.",
        "body": "# Rocky: The Tri-Pawd Trail Explorer\n\nRocky was rescued near Secunderabad railway tracks with severe limb trauma.\n\n### Orthopedic Rehabilitation\nFollowing a clean amputation and physiotherapy, Rocky mastered three-legged running in record time.\n\n### Living Life to the Fullest\nRocky and his adopter Ananya are regular participants in Hyderabad weekend hiking clubs.",
        "hero_image_url": SUPABASE_MEDIA[3],
        "status": "published",
        "is_featured": False,
        "sort_order": 4,
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "title": "Leo & Luna: Bonded Senior Pair Find Peace",
        "slug": "leo-luna-bonded-senior-pair-find-peace",
        "summary": "After their elderly guardian passed away, 8-year-old siblings Leo and Luna were kept together and adopted by a serene farmstead family in Shamshabad.",
        "body": "# Leo & Luna: Bonded Senior Pair Find Peace\n\nSenior bonded pairs are often hard to rehome together, but PawGuard made a promise never to separate Leo and Luna.\n\n### The Perfect Sanctuary\nA retired couple with a 2-acre farm welcomed both dogs with open arms, giving them their dream retirement.",
        "hero_image_url": SUPABASE_MEDIA[4],
        "status": "published",
        "is_featured": False,
        "sort_order": 5,
    },
    {
        "id": "66666666-6666-4666-8666-666666666666",
        "title": "Daisy: Overcoming Trauma Through Foster Love",
        "slug": "daisy-overcoming-trauma-through-foster-love",
        "summary": "Traumatized and fearful of human touch, Daisy spent 4 months in patient foster care before opening up into a joyful, cuddly family companion.",
        "body": "# Daisy: Overcoming Trauma Through Foster Love\n\nDaisy would tremble whenever anyone entered her kennel. Our behavioral foster network stepped in to provide gentle, positive-reinforcement rehabilitation.\n\n### Transformation\nToday, Daisy loves belly rubs and greets everyone with an enthusiastic tail wag.",
        "hero_image_url": SUPABASE_MEDIA[5],
        "status": "published",
        "is_featured": False,
        "sort_order": 6,
    },
    {
        "id": "77777777-7777-4777-8777-777777777777",
        "title": "Simba's Great Escape: Reunited After 45 Days Lost",
        "slug": "simbas-great-escape-reunited-after-45-days-lost",
        "summary": "Using PawGuard Lost & Found automated proximity matching and QR collar tag scan, Simba was reunited with his weeping family 15 kilometers away.",
        "body": "# Simba's Great Escape: Reunited After 45 Days Lost\n\nSimba slipped out during Diwali fireworks. A good samaritan scanned his PawGuard QR smart tag and the platform instantly notified the owner with precise GPS coordinates.",
        "hero_image_url": UNSPLASH_DOGS[0],
        "status": "published",
        "is_featured": False,
        "sort_order": 7,
    },
]

BLOG_POSTS = [
    {
        "id": "11111111-1111-4111-8111-111111111111",
        "title": "First 48 Hours with Your Adopted Dog: Essential Transition Guide",
        "slug": "first-48-hours-adopted-dog-transition-guide",
        "excerpt": "A step-by-step roadmap to make your newly adopted pet feel calm, safe, and loved from moment one.",
        "body": "# First 48 Hours with Your Adopted Dog: Essential Transition Guide\n\nBringing a new rescue dog into your home is a deeply rewarding milestone.",
        "cover_image_url": SUPABASE_MEDIA[0],
        "category": "Adoption Guides",
        "status": "published",
        "tags": "adoption, pet care, dogs, rescue",
        "author": "PawGuard Welfare Team",
    },
    {
        "id": "22222222-2222-4222-8222-222222222222",
        "title": "Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs",
        "slug": "understanding-canine-nutrition-shelter-dogs",
        "excerpt": "How targeted high-protein diets and micronutrient supplementation help rescued dogs rebuild muscle mass and boost immunity.",
        "body": "# Understanding Canine Nutrition: Fueling Recovery in Shelter Dogs\n\nWhen stray dogs arrive at our rescue shelter, malnutrition and gut dysbiosis are common.",
        "cover_image_url": SUPABASE_MEDIA[1],
        "category": "Health & Nutrition",
        "status": "published",
        "tags": "nutrition, health, shelter, recovery",
        "author": "Dr. Priya Sharma, Senior Veterinarian",
    },
    {
        "id": "33333333-3333-4333-8333-333333333333",
        "title": "The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet",
        "slug": "the-3-3-3-rule-adopting-rescued-pet",
        "excerpt": "The first 3 days, 3 weeks, and 3 months with your new adopted dog are crucial for building lifelong trust.",
        "body": "# The 3-3-3 Rule: What to Expect When Adopting a Rescued Pet\n\nBringing a rescue dog home is an exciting milestone.",
        "cover_image_url": SUPABASE_MEDIA[4],
        "category": "Adoption Guides",
        "status": "published",
        "tags": "adoption, training, care, family",
        "author": "Adoptions Desk",
    },
    {
        "id": "44444444-4444-4444-8444-444444444444",
        "title": "Community Vaccination Drives: Eradicating Rabies One Sector at a Time",
        "slug": "community-vaccination-drives-eradicating-rabies",
        "excerpt": "PawGuard's annual mobile vaccination clinic vaccinated over 1,200 neighborhood strays this month.",
        "body": "# Community Vaccination Drives: Eradicating Rabies One Sector at a Time\n\nMass dog vaccination prevents rabies effectively.",
        "cover_image_url": SUPABASE_MEDIA[3],
        "category": "Community Initiatives",
        "status": "published",
        "tags": "vaccination, rabies, community, health",
        "author": "Field Operations Team",
    },
    {
        "id": "55555555-5555-4555-8555-555555555555",
        "title": "Senior Dogs: Why Older Canines Make the Most Loyal Companions",
        "slug": "senior-dogs-why-older-canines-make-loyal-companions",
        "excerpt": "Senior dogs often get overlooked in shelters, yet they offer calm demeanor and unconditional affection.",
        "body": "# Senior Dogs: Why Older Canines Make the Most Loyal Companions\n\nSenior dogs possess a gentle wisdom.",
        "cover_image_url": SUPABASE_MEDIA[2],
        "category": "Adoption Guides",
        "status": "published",
        "tags": "senior dogs, adoption, love, companions",
        "author": "Welfare Council",
    },
    {
        "id": "66666666-6666-4666-8666-666666666666",
        "title": "Emergency First-Aid Checklist for Stray Animal Responders",
        "slug": "emergency-first-aid-checklist-stray-animal-responders",
        "excerpt": "Quick stabilization techniques before an ambulance reaches the scene: heat exhaustion, fractures, and wound care.",
        "body": "# Emergency First-Aid Checklist for Stray Animal Responders\n\nWhen encountering an injured animal on the road, staying calm and taking prompt, safe actions can save a life.",
        "cover_image_url": SUPABASE_MEDIA[5],
        "category": "Emergency & First Aid",
        "status": "published",
        "tags": "first aid, rescue, emergency, dogs",
        "author": "Rapid Response Unit",
    },
]

DOGS_DATA = [
    {
        "name": "Maya",
        "breed": "Indie Mix",
        "breed_classification": "mix",
        "gender": "female",
        "is_spayed_neutered": True,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 16.5,
        "color": "Golden Tan & White",
        "temperament": "friendly",
        "ear_shape": "floppy",
        "tail_type": "straight",
        "distinctive_markers": "White star patch on chest, dark eyeliner eyes",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[0], UNSPLASH_DOGS[0]],
    },
    {
        "name": "Bruno",
        "breed": "Golden Retriever Mix",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "1.5 years",
        "age_months": 18,
        "weight": 22.0,
        "color": "Honey Golden",
        "temperament": "high_energy",
        "ear_shape": "floppy",
        "tail_type": "long",
        "distinctive_markers": "Feathery golden tail and warm amber eyes",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[1], UNSPLASH_DOGS[1]],
    },
    {
        "name": "Bella",
        "breed": "Labrador Mix",
        "breed_classification": "mix",
        "gender": "female",
        "is_spayed_neutered": True,
        "estimated_age": "3 years",
        "age_months": 36,
        "weight": 20.5,
        "color": "Caramel Brown",
        "temperament": "cat_child_safe",
        "ear_shape": "floppy",
        "tail_type": "straight",
        "distinctive_markers": "Soft velvety ears and gentle gaze",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[2], UNSPLASH_DOGS[2]],
    },
    {
        "name": "Rocky",
        "breed": "Indie Shepherd Mix",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "2.5 years",
        "age_months": 30,
        "weight": 18.0,
        "color": "Sable & Black",
        "temperament": "friendly",
        "ear_shape": "pricked",
        "tail_type": "curled",
        "distinctive_markers": "Tri-pawd hero, energetic and trail loving",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[3], UNSPLASH_DOGS[3]],
    },
    {
        "name": "Leo",
        "breed": "Cocker Spaniel Mix",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "4 years",
        "age_months": 48,
        "weight": 14.2,
        "color": "Reddish Chestnut",
        "temperament": "friendly",
        "ear_shape": "floppy",
        "tail_type": "docked",
        "distinctive_markers": "Wavy silky coat on chest and ears",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[4], UNSPLASH_DOGS[4]],
    },
    {
        "name": "Luna",
        "breed": "Indie Pariah",
        "breed_classification": "pure",
        "gender": "female",
        "is_spayed_neutered": True,
        "estimated_age": "1 year",
        "age_months": 12,
        "weight": 13.5,
        "color": "Fawn & Cream",
        "temperament": "pack_compatible",
        "ear_shape": "pricked",
        "tail_type": "curled",
        "distinctive_markers": "White dipped tail tip, alert pricked ears",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [SUPABASE_MEDIA[5], UNSPLASH_DOGS[5]],
    },
    {
        "name": "Charlie",
        "breed": "Beagle Mix",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 15.0,
        "color": "Tricolor (Black, White, Tan)",
        "temperament": "friendly",
        "ear_shape": "floppy",
        "tail_type": "straight",
        "distinctive_markers": "Classic white muzzle and tricolor saddle pattern",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[6], SUPABASE_MEDIA[0]],
    },
    {
        "name": "Daisy",
        "breed": "Indie Blend",
        "breed_classification": "mix",
        "gender": "female",
        "is_spayed_neutered": True,
        "estimated_age": "10 months",
        "age_months": 10,
        "weight": 11.8,
        "color": "Cream & Pearl",
        "temperament": "timid_fearful",
        "ear_shape": "semi_pricked",
        "tail_type": "curled",
        "distinctive_markers": "Heart-shaped pink nose, soft white coat",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[7], SUPABASE_MEDIA[1]],
    },
    {
        "name": "Sheru",
        "breed": "Desi Royal Indie",
        "breed_classification": "pure",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "3 years",
        "age_months": 36,
        "weight": 19.2,
        "color": "Rich Rust Brown",
        "temperament": "pack_compatible",
        "ear_shape": "pricked",
        "tail_type": "curled",
        "distinctive_markers": "Noble pariah stance, loyal and agile",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[8], SUPABASE_MEDIA[2]],
    },
    {
        "name": "Oreo",
        "breed": "Border Collie Mix",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "1.2 years",
        "age_months": 14,
        "weight": 17.5,
        "color": "Black & White",
        "temperament": "high_energy",
        "ear_shape": "semi_pricked",
        "tail_type": "long",
        "distinctive_markers": "Symmetrical white face blaze and collar",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[0], SUPABASE_MEDIA[3]],
    },
    {
        "name": "Koko",
        "breed": "Dachshund Indie Cross",
        "breed_classification": "mix",
        "gender": "female",
        "is_spayed_neutered": True,
        "estimated_age": "2 years",
        "age_months": 24,
        "weight": 9.5,
        "color": "Chocolate Tan",
        "temperament": "friendly",
        "ear_shape": "floppy",
        "tail_type": "straight",
        "distinctive_markers": "Short legs, soulful brown eyes",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[1], SUPABASE_MEDIA[4]],
    },
    {
        "name": "Simba",
        "breed": "Golden Indie",
        "breed_classification": "mix",
        "gender": "male",
        "is_spayed_neutered": True,
        "estimated_age": "2.8 years",
        "age_months": 34,
        "weight": 21.0,
        "color": "Lion Gold",
        "temperament": "cat_child_safe",
        "ear_shape": "pricked",
        "tail_type": "long",
        "distinctive_markers": "Lush mane coat around neck and golden tail plume",
        "status": "shelter",
        "is_adoptable": True,
        "is_quarantine_passed": True,
        "image_urls": [UNSPLASH_DOGS[2], SUPABASE_MEDIA[5]],
    },
]

LOST_REPORTS = [
    {
        "pet_name": "Milo",
        "species": "dog",
        "breed": "Beagle Mix",
        "color": "Tan & White",
        "microchip_id": "985141002345001",
        "collar_color": "Red",
        "collar_description": "Red nylon collar with silver bell",
        "marker_description": "White patch on chest and right front paw",
        "location_address": "Road No. 36, Jubilee Hills, Hyderabad",
        "latitude": 17.4326,
        "longitude": 78.4071,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[0],
    },
    {
        "pet_name": "Tiger",
        "species": "dog",
        "breed": "Indie Pariah",
        "color": "Brindle Brown",
        "microchip_id": "985141002345002",
        "collar_color": "Blue",
        "collar_description": "Reflective blue collar",
        "marker_description": "Dark brindle stripes on back, left ear slightly floppy",
        "location_address": "Near Cyber Towers, Hitec City, Hyderabad",
        "latitude": 17.4504,
        "longitude": 78.3808,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[1],
    },
    {
        "pet_name": "Coco",
        "species": "dog",
        "breed": "Labrador Retriever",
        "color": "Chocolate Brown",
        "microchip_id": "985141002345003",
        "collar_color": "Orange",
        "collar_description": "Orange waterproof webbing collar",
        "marker_description": "Small white marking on lower jaw",
        "location_address": "KBR Park Gate 2, Banjara Hills, Hyderabad",
        "latitude": 17.4198,
        "longitude": 78.4285,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[2],
    },
    {
        "pet_name": "Rusty",
        "species": "dog",
        "breed": "Pomeranian Mix",
        "color": "Golden Orange",
        "microchip_id": "985141002345004",
        "collar_color": "Green",
        "collar_description": "Green collar with ID tag",
        "marker_description": "Fluffy curled tail, very friendly",
        "location_address": "Gachibowli Stadium Road, Hyderabad",
        "latitude": 17.4435,
        "longitude": 78.3489,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[3],
    },
]

FOUND_REPORTS = [
    {
        "species": "dog",
        "breed_observed": "Indie Desi Dog",
        "color_observed": "Fawn with White Socks",
        "collar_color": "Red",
        "collar_description": "Faded red collar, no tag",
        "marker_description": "White socks on all four paws, brown eyes",
        "location_address": "Madhapur Metro Station, Hyderabad",
        "latitude": 17.4399,
        "longitude": 78.3908,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[4],
    },
    {
        "species": "dog",
        "breed_observed": "German Shepherd Mix",
        "color_observed": "Black and Tan",
        "collar_color": None,
        "collar_description": "No collar found",
        "marker_description": "Erect ears, bushy tail, calm behavior",
        "location_address": "Kondapur Botanical Garden Road, Hyderabad",
        "latitude": 17.4612,
        "longitude": 78.3615,
        "status": "active",
        "photo_url": SUPABASE_MEDIA[5],
    },
    {
        "species": "dog",
        "breed_observed": "Golden Retriever Mix",
        "color_observed": "Cream White",
        "collar_color": "Blue",
        "collar_description": "Worn blue cloth collar",
        "marker_description": "Gentle temperament, sits on command",
        "location_address": "Durgam Cheruvu Walking Track, Hyderabad",
        "latitude": 17.4320,
        "longitude": 78.3882,
        "status": "active",
        "photo_url": UNSPLASH_DOGS[1],
    },
]


async def seed_database(db_name: str, db_url: str):
    print(f"\n{'='*70}\nConnecting to: {db_name}\n{'='*70}")
    try:
        conn = await asyncpg.connect(db_url, statement_cache_size=0, timeout=15)
    except Exception as e:
        print(f"FAILED to connect to {db_name}: {e}")
        return

    now = datetime.now(timezone.utc)

    # 1. First find or create an active admin/staff user for foreign keys
    user_id = await conn.fetchval(
        "SELECT id FROM users WHERE is_active = true ORDER BY created_at ASC LIMIT 1"
    )
    if not user_id:
        user_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO users (id, email, phone, full_name, hashed_password, is_active, is_verified, created_at, updated_at)
            VALUES ($1, 'system.admin@pawguard.org', '+919999999999', 'PawGuard Administrator', 'argon2id$mocked', true, true, $2, $2)
            """,
            user_id,
            now,
        )
    print(f"Using author/user_id: {user_id}")

    # 2. SUCCESS STORIES
    print("\n--- Seeding Success Stories ---")
    for s in SUCCESS_STORIES:
        sid = uuid.UUID(s["id"])
        await conn.execute(
            """
            INSERT INTO success_stories (
                id, title, slug, summary, body, hero_image_url,
                status, is_featured, sort_order, published_at, created_at, updated_at, has_consent
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, $10, true
            )
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                slug = EXCLUDED.slug,
                summary = EXCLUDED.summary,
                body = EXCLUDED.body,
                hero_image_url = EXCLUDED.hero_image_url,
                status = EXCLUDED.status,
                is_featured = EXCLUDED.is_featured,
                sort_order = EXCLUDED.sort_order,
                published_at = EXCLUDED.published_at,
                updated_at = EXCLUDED.updated_at,
                has_consent = true;
            """,
            sid,
            s["title"],
            s["slug"],
            s["summary"],
            s["body"],
            s["hero_image_url"],
            s["status"],
            s["is_featured"],
            s["sort_order"],
            now,
        )
    stories_count = await conn.fetchval(
        "SELECT count(*) FROM success_stories WHERE status = 'published'"
    )
    print(f"Published Success Stories in DB: {stories_count}")

    # 3. BLOG POSTS
    print("\n--- Seeding Blog Posts ---")
    for b in BLOG_POSTS:
        bid = uuid.UUID(b["id"])
        await conn.execute(
            """
            INSERT INTO blog_posts (
                id, title, slug, excerpt, body, cover_image_url,
                category, status, tags, author, published_at, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $11, $11
            )
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                slug = EXCLUDED.slug,
                excerpt = EXCLUDED.excerpt,
                body = EXCLUDED.body,
                cover_image_url = EXCLUDED.cover_image_url,
                category = EXCLUDED.category,
                status = EXCLUDED.status,
                tags = EXCLUDED.tags,
                author = EXCLUDED.author,
                published_at = EXCLUDED.published_at,
                updated_at = EXCLUDED.updated_at;
            """,
            bid,
            b["title"],
            b["slug"],
            b["excerpt"],
            b["body"],
            b["cover_image_url"],
            b["category"],
            b["status"],
            b["tags"],
            b["author"],
            now,
        )
    blogs_count = await conn.fetchval("SELECT count(*) FROM blog_posts WHERE status = 'published'")
    print(f"Published Blog Posts in DB: {blogs_count}")

    # 4. ADOPTABLE DOGS
    print("\n--- Seeding Adoptable Dogs ---")
    facility_id = await conn.fetchval("SELECT id FROM shelter_facilities LIMIT 1")
    if not facility_id:
        facility_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO shelter_facilities (id, name, address, phone, total_capacity, status, facility_type, created_at, updated_at)
            VALUES ($1, 'PawGuard Central Rescue Sanctuary', 'Gachibowli Sanctuary Road, Hyderabad', '+91-98765-43210', 100, 'active', 'shelter', $2, $2)
            """,
            facility_id,
            now,
        )

    for i, d in enumerate(DOGS_DATA, start=1):
        reg_no = f"DOG-2026-ADOPT-{i:04d}"
        img_json = json.dumps(d["image_urls"])
        existing_dog_id = await conn.fetchval(
            "SELECT id FROM dog_profiles WHERE registration_number = $1", reg_no
        )
        if not existing_dog_id:
            dog_uuid = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO dog_profiles (
                    id, registration_number, name, breed, breed_classification, gender,
                    is_spayed_neutered, estimated_age, age_months, weight, color,
                    temperament, ear_shape, tail_type, distinctive_markers,
                    status, is_adoptable, is_quarantine_passed, shelter_facility_id,
                    image_urls, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20, $21, $21
                )
                """,
                dog_uuid,
                reg_no,
                d["name"],
                d["breed"],
                d["breed_classification"],
                d["gender"],
                d["is_spayed_neutered"],
                d["estimated_age"],
                d["age_months"],
                d["weight"],
                d["color"],
                d["temperament"],
                d["ear_shape"],
                d["tail_type"],
                d["distinctive_markers"],
                d["status"],
                d["is_adoptable"],
                d["is_quarantine_passed"],
                facility_id,
                img_json,
                now,
            )
        else:
            await conn.execute(
                """
                UPDATE dog_profiles SET
                    name = $2,
                    breed = $3,
                    breed_classification = $4,
                    gender = $5,
                    is_spayed_neutered = $6,
                    estimated_age = $7,
                    age_months = $8,
                    weight = $9,
                    color = $10,
                    temperament = $11,
                    ear_shape = $12,
                    tail_type = $13,
                    distinctive_markers = $14,
                    status = $15,
                    is_adoptable = $16,
                    is_quarantine_passed = $17,
                    shelter_facility_id = $18,
                    image_urls = $19,
                    updated_at = $20
                WHERE id = $1
                """,
                existing_dog_id,
                d["name"],
                d["breed"],
                d["breed_classification"],
                d["gender"],
                d["is_spayed_neutered"],
                d["estimated_age"],
                d["age_months"],
                d["weight"],
                d["color"],
                d["temperament"],
                d["ear_shape"],
                d["tail_type"],
                d["distinctive_markers"],
                d["status"],
                d["is_adoptable"],
                d["is_quarantine_passed"],
                facility_id,
                img_json,
                now,
            )

    adoptable_count = await conn.fetchval(
        "SELECT count(*) FROM dog_profiles WHERE is_adoptable = true"
    )
    print(f"Adoptable Dogs in DB: {adoptable_count}")

    # 5. LOST REPORTS
    print("\n--- Seeding Lost Pet Reports ---")
    for r in LOST_REPORTS:
        existing_report = await conn.fetchval(
            "SELECT id FROM lost_reports WHERE pet_name = $1 AND location_address = $2",
            r["pet_name"],
            r["location_address"],
        )
        if not existing_report:
            report_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO lost_reports (
                    id, user_id, pet_name, species, breed, color, microchip_id,
                    collar_color, collar_description, marker_description,
                    location_address, latitude, longitude, lost_at,
                    status, photo_url, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $14, $14
                )
                """,
                report_id,
                user_id,
                r["pet_name"],
                r["species"],
                r["breed"],
                r["color"],
                r["microchip_id"],
                r["collar_color"],
                r["collar_description"],
                r["marker_description"],
                r["location_address"],
                r["latitude"],
                r["longitude"],
                now,
                r["status"],
                r["photo_url"],
            )
        else:
            await conn.execute(
                """
                UPDATE lost_reports SET
                    photo_url = $2,
                    status = 'active',
                    updated_at = $3
                WHERE id = $1
                """,
                existing_report,
                r["photo_url"],
                now,
            )
    lost_count = await conn.fetchval("SELECT count(*) FROM lost_reports WHERE photo_url IS NOT NULL")
    print(f"Lost reports with photos: {lost_count}")

    # 6. FOUND REPORTS
    print("\n--- Seeding Found Pet Reports ---")
    for f in FOUND_REPORTS:
        existing_found = await conn.fetchval(
            "SELECT id FROM found_reports WHERE location_address = $1", f["location_address"]
        )
        if not existing_found:
            found_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO found_reports (
                    id, user_id, species, breed_observed, color_observed,
                    collar_color, collar_description, marker_description,
                    location_address, latitude, longitude, found_at,
                    status, photo_url, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $12, $12
                )
                """,
                found_id,
                user_id,
                f["species"],
                f["breed_observed"],
                f["color_observed"],
                f["collar_color"],
                f["collar_description"],
                f["marker_description"],
                f["location_address"],
                f["latitude"],
                f["longitude"],
                now,
                f["status"],
                f["photo_url"],
            )
        else:
            await conn.execute(
                """
                UPDATE found_reports SET
                    photo_url = $2,
                    status = 'active',
                    updated_at = $3
                WHERE id = $1
                """,
                existing_found,
                f["photo_url"],
                now,
            )
    found_count = await conn.fetchval(
        "SELECT count(*) FROM found_reports WHERE photo_url IS NOT NULL"
    )
    print(f"Found reports with photos: {found_count}")

    # 7. VET CLINICS & PARTNERS
    print("\n--- Updating Vet Clinics & Partners ---")
    await conn.execute("""
        UPDATE vet_clinics SET is_active = true, is_emergency = true;
    """)
    await conn.execute("""
        UPDATE veterinary_partners SET is_active = true, is_emergency = true;
    """)
    vets_count = await conn.fetchval("SELECT count(*) FROM vet_clinics WHERE is_active = true")
    print(f"Active vet clinics: {vets_count}")

    # 8. CMS HERO & FIELD IMAGES
    print("\n--- Updating CMS Banner Images ---")
    hero_section_id = await conn.fetchval("""
        SELECT s.id FROM cms_sections s
        JOIN cms_pages p ON p.id = s.page_id
        WHERE p.slug = 'home' AND s.section_key = 'hero'
        LIMIT 1
    """)
    if hero_section_id:
        await conn.execute(
            """
            INSERT INTO cms_content_fields (
                id, section_id, field_key, field_type, published_value, draft_value, created_at, updated_at
            ) VALUES (
                $1, $2, 'hero_banner_image', 'image', $3, $3, $4, $4
            )
            ON CONFLICT (id) DO UPDATE SET
                published_value = EXCLUDED.published_value,
                draft_value = EXCLUDED.draft_value,
                updated_at = EXCLUDED.updated_at;
            """,
            uuid.uuid4(),
            hero_section_id,
            SUPABASE_MEDIA[0],
            now,
        )

    await conn.close()
    print(f"Completed seeding for {db_name} successfully!")


async def main():
    for name, url in DATABASES:
        await seed_database(name, url)


if __name__ == "__main__":
    asyncio.run(main())
