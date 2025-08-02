# app/models/base.py
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from google.protobuf.timestamp_pb2 import Timestamp

class DocumentInDB(BaseModel):
    id: str = Field(..., description="Firestore document ID")
    created_at: Optional[datetime] = None

    @classmethod
    def convert_timestamp_to_datetime(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        if 'created_at' in data and isinstance(data['created_at'], Timestamp):
            data['created_at'] = data['created_at'].astimezone(datetime.now().astimezone().tzinfo)
        if 'published_at' in data and isinstance(data['published_at'], Timestamp):
            data['published_at'] = data['published_at'].astimezone(datetime.now().astimezone().tzinfo)
        if 'timestamp' in data and isinstance(data['timestamp'], Timestamp):
            data['timestamp'] = data['timestamp'].astimezone(datetime.now().astimezone().tzinfo)
        if 'location_history' in data and isinstance(data['location_history'], list):
            for entry in data['location_history']:
                if 'timestamp' in entry and isinstance(entry['timestamp'], Timestamp):
                    entry['timestamp'] = entry['timestamp'].astimezone(datetime.now().astimezone().tzinfo)
        return data
