from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
class UserUpdate(BaseModel):
    model_config = ConfigDict(
        extra = "forbid",
        str_strip_whitespace = True
    )
    display_name:str|None =Field(
        default = None,
        min_length = 2,
        max_length = 50,
    )
class UserResponse(BaseModel):
    model_config = ConfigDict(
        from_attributes = True
    )
    id:UUID
    display_name:str|None
    role:str
    created_at:datetime
    updated_at:datetime
