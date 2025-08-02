# campulse-backend/app/core/geopoint.py
from pydantic import BaseModel, Field
from google.cloud.firestore import GeoPoint

class GeoPointModel(BaseModel):
    latitude: float = Field(..., alias="_latitude")
    longitude: float = Field(..., alias="_longitude")

    @classmethod
    def __get_validators__(cls):
        yield cls.validate_geopoint

    @classmethod
    def validate_geopoint(cls, v):
        if isinstance(v, GeoPoint):
            return cls(latitude=v.latitude, longitude=v.longitude)
        elif isinstance(v, dict):
            # Accept both alias and non-alias keys
            if 'latitude' in v and 'longitude' in v:
                return cls(latitude=v['latitude'], longitude=v['longitude'])
            elif '_latitude' in v and '_longitude' in v:
                return cls(latitude=v['_latitude'], longitude=v['_longitude'])
        raise ValueError("Invalid GeoPoint format")

    def to_firestore_geopoint(self) -> GeoPoint:
        return GeoPoint(self.latitude, self.longitude)

    def model_dump(self, *args, **kwargs):
        data = super().model_dump(*args, **kwargs)
        data["_latitude"] = data.pop("latitude")
        data["_longitude"] = data.pop("longitude")
        return data