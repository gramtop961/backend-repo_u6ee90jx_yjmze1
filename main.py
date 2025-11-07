import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response


def _search_itunes(term: str, limit: int = 20):
    url = "https://itunes.apple.com/search"
    params = {"term": term, "media": "music", "entity": "song", "limit": limit}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])


def _lookup_similar_by_artist(artist: str, exclude_track_id: int | None = None, limit: int = 12):
    results = _search_itunes(artist, limit=50)
    items = []
    seen = set()
    for it in results:
        if it.get("kind") != "song":
            continue
        track_id = it.get("trackId")
        if exclude_track_id and track_id == exclude_track_id:
            continue
        key = (it.get("trackName"), it.get("artistName"))
        if key in seen:
            continue
        seen.add(key)
        items.append(it)
        if len(items) >= limit:
            break
    return items


@app.get("/api/similar")
def get_similar_songs(song: str = Query(..., description="Song name to find similar tracks for")):
    # Step 1: find the seed track
    seed_results = _search_itunes(song, limit=25)
    seed = None
    for it in seed_results:
        if it.get("kind") == "song":
            seed = it
            break
    if not seed:
        raise HTTPException(status_code=404, detail="Song not found. Try a different name.")

    artist = seed.get("artistName")
    track_id = seed.get("trackId")

    # Step 2: fetch more by same artist as a simple, keyless heuristic
    similar = _lookup_similar_by_artist(artist, exclude_track_id=track_id, limit=16)

    # If too few, broaden by including the seed term again (captures covers/remixes)
    if len(similar) < 8:
        extra = _search_itunes(song, limit=50)
        for it in extra:
            if it.get("kind") != "song":
                continue
            if it.get("trackId") == track_id:
                continue
            key = (it.get("trackName"), it.get("artistName"))
            if all((it.get("trackName"), it.get("artistName")) != (x.get("trackName"), x.get("artistName")) for x in similar):
                similar.append(it)
            if len(similar) >= 16:
                break

    # Shape response
    def map_item(it):
        return {
            "trackId": it.get("trackId"),
            "trackName": it.get("trackName"),
            "artistName": it.get("artistName"),
            "collectionName": it.get("collectionName"),
            "artworkUrl100": it.get("artworkUrl100"),
            "previewUrl": it.get("previewUrl"),
            "trackViewUrl": it.get("trackViewUrl"),
        }

    payload = {
        "seed": map_item(seed),
        "similar": [map_item(x) for x in similar[:16]],
    }
    return payload


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
