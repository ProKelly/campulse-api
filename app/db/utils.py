from typing import Dict, Any, Type
from google.cloud.firestore import GeoPoint
from app.models.base import DocumentInDB
from datetime import datetime
import math

def convert_doc_to_model(doc_id: str, doc_data: Dict[str, Any], Model: Type) -> Any:
    try:
        # Ensure all datetime fields are serialized to strings
        for key, value in doc_data.items():
            if isinstance(value, datetime):
                doc_data[key] = value.isoformat()
            elif isinstance(value, GeoPoint):
                # Convert GeoPoint to dictionary
                doc_data[key] = {"_latitude": value.latitude, "_longitude": value.longitude}
            elif isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, datetime):
                        value[sub_key] = sub_value.isoformat()
                    elif isinstance(sub_value, GeoPoint):
                        value[sub_key] = {"_latitude": sub_value.latitude, "_longitude": sub_value.longitude}
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        for sub_key, sub_value in item.items():
                            if isinstance(sub_value, datetime):
                                item[sub_key] = sub_value.isoformat()
                            elif isinstance(sub_value, GeoPoint):
                                item[sub_key] = {"_latitude": sub_value.latitude, "_longitude": sub_value.longitude}

        # Handle Firestore sentinel values (e.g., SERVER_TIMESTAMP)
        for key, value in doc_data.items():
            if str(value).startswith("Sentinel"):  # Check for sentinel values
                doc_data[key] = "SERVER_TIMESTAMP"  # Replace with a string for serialization

        data = {"id": doc_id, **doc_data}
        data = DocumentInDB.convert_timestamp_to_datetime(data)
        return Model.model_validate(data)
    except Exception as e:
        print("Error in convert_doc_to_model:", e)  # Debugging log
        raise


def bounding_box(lat, lon, radius):
    """
    Returns the bounding box coordinates for a given lat/lon and radius in meters.
    """
    R = 6378137.0  # Earth radius in meters
    d_lat = radius / R
    d_lon = radius / (R * math.cos(math.pi * lat / 180))

    min_lat = lat - d_lat * 180 / math.pi
    max_lat = lat + d_lat * 180 / math.pi
    min_lon = lon - d_lon * 180 / math.pi
    max_lon = lon + d_lon * 180 / math.pi

    return (min_lat, min_lon, max_lat, max_lon)