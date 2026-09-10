"""Migrate and replace broken dog.ceo URLs with valid, hosted PawGuard media assets."""

import json
import urllib.request
import urllib.error

base_url = "https://pawguard-backend-dev.onrender.com"

# Hosted valid dog images
VALID_HOSTED_DOG_IMAGES = [
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/adoption%20images/pexels-kyoz-27732479.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-anny-patterson-2163004403-38626454.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-mohit-chanderh-129199578-18109070.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-humanistagram-12732006.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-gustavodenuncio-26607813.jpg",
    "https://rsllewhpzxpdstmjhmxj.storage.supabase.co/storage/v1/object/public/pawguard-media/blog%20success%20stories/pexels-evlivanburak-10996406.jpg",
]


def run_migration():
    print(f"Starting Dog CEO URL migration against: {base_url}")

    # 1. Login as Shelter Manager / Admin
    login_payload = json.dumps(
        {"email": "shelter.manager@pawguard.com", "password": "PawGuard@2026"}
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{base_url}/api/v1/auth/login",
        data=login_payload,
        headers={"Content-Type": "application/json", "User-Agent": "PawGuard-Migrator"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode())
        token = res["data"]["access_token"]
        print("Logged in as super.admin successfully.")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "PawGuard-Migrator",
    }

    # 2. Fetch dogs across all statuses
    statuses = [None, "shelter", "fostered", "rescued", "clinic", "adopted"]
    seen_ids = set()
    dogs = []
    for st in statuses:
        url = f"{base_url}/api/v1/dogs?limit=50" + (f"&status={st}" if st else "")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
            batch = res["data"] if isinstance(res["data"], list) else res["data"].get("items", [])
            for d in batch:
                if d["id"] not in seen_ids:
                    seen_ids.add(d["id"])
                    dogs.append(d)

    print(f"Fetched {len(dogs)} unique dogs across all statuses. Inspecting image URLs...")

    updated_count = 0
    for idx, dog in enumerate(dogs):
        dog_id = dog["id"]
        name = dog["name"]
        photos = dog.get("image_urls") or []
        has_broken = any("dog.ceo" in str(u).lower() for u in photos)

        if has_broken:
            replacement_img = VALID_HOSTED_DOG_IMAGES[idx % len(VALID_HOSTED_DOG_IMAGES)]
            print(f"Dog '{name}' ({dog_id}) has broken dog.ceo URLs: {photos}")
            print(f"  -> Replacing with valid image: {replacement_img}")

            patch_payload = json.dumps({"image_urls": [replacement_img]}).encode("utf-8")

            patch_req = urllib.request.Request(
                f"{base_url}/api/v1/dogs/{dog_id}",
                data=patch_payload,
                headers=headers,
                method="PUT",
            )
            try:
                with urllib.request.urlopen(patch_req, timeout=15) as patch_resp:
                    patch_res = json.loads(patch_resp.read().decode())
                    print(
                        f"  -> Successfully updated '{name}'! New photo_url: {patch_res['data'].get('photo_url')}"
                    )
                    updated_count += 1
            except urllib.error.HTTPError as e:
                print(f"  -> Failed to update '{name}': {e.code} - {e.read().decode()}")

    print(f"\nMigration complete. Total dogs updated: {updated_count}")


if __name__ == "__main__":
    run_migration()
