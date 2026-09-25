from pydantic import BaseModel,Field
class HighlightRequest(BaseModel):
    segments:list[dict]=Field(default_factory=list)
    min_seconds:float=Field(15,ge=5,le=120)
    max_seconds:float=Field(60,ge=10,le=300)
    limit:int=Field(5,ge=1,le=20)
