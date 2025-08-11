import geohash2
from google.cloud import firestore
from app.config import db

GOOGLE_APPLICATION_CREDENTIALS = "./serviceAccountKey.json"

# Initialize Firestore client
def migrate_institution_posts():
    posts_ref = db.collection("institution_posts")
    docs = posts_ref.stream()

    updated_count = 0
    skipped_count = 0
    error_count = 0

    for doc in docs:
        try:
            post_data = doc.to_dict()

            # Skip if geohash already exists
            if "geohash" in post_data:
                skipped_count += 1
                continue

            # Skip if map_location is missing
            if "map_location" not in post_data:
                skipped_count += 1
                continue

            lat = post_data["map_location"].get("lat")
            lng = post_data["map_location"].get("lng")

            if lat is None or lng is None:
                skipped_count += 1
                continue

            # Generate geohash (precision 9 ≈ ~5 meters)
            geohash_value = geohash2.encode(lat, lng, precision=9)

            # Update document with new geohash
            posts_ref.document(doc.id).update({
                "geohash": geohash_value
            })

            updated_count += 1
            print(f"✅ Updated {doc.id} with geohash {geohash_value}")

        except Exception as e:
            error_count += 1
            print(f"❌ Error updating {doc.id}: {e}")

    print("\n--- Migration Complete ---")
    print(f"Updated: {updated_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")


if __name__ == "__main__":
    migrate_institution_posts()
