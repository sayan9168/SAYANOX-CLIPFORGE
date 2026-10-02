"""Bounded, finite request models shared by uploads, rendering and projects."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, model_validator

JobId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
FiniteTime = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Signal = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Duration = Annotated[int, Field(ge=5, le=180, strict=True)]
Aspect = Literal["9:16", "1:1", "16:9"]
CaptionStyle = Literal["default", "karaoke", "clean", "bold", "bengali", "hindi"]


class AnalysisOptions(BaseModel):
    min_seconds: float = Field(15, ge=5, le=180, allow_inf_nan=False)
    max_seconds: float = Field(90, ge=5, le=180, allow_inf_nan=False)
    limit: int = Field(8, ge=1, le=20)

    @model_validator(mode="after")
    def check_order(self):
        if self.max_seconds < self.min_seconds:
            raise ValueError("max_seconds must be >= min_seconds")
        return self


class ClipWindow(BaseModel):
    start: FiniteTime
    end: FiniteTime

    @model_validator(mode="after")
    def check_window(self):
        if self.end <= self.start or self.end - self.start > 180:
            raise ValueError("Clip end must be after its start, with a maximum length of 180 seconds")
        return self


class HighlightSelection(ClipWindow):
    title: str = Field("", max_length=200)
    text: str = Field("", max_length=20000)
    score: float | None = Field(None, ge=0, le=100, allow_inf_nan=False)
    locked: StrictBool = False
    selected: StrictBool = True


class RenderSettings(BaseModel):
    durations: list[Duration] = Field(default_factory=lambda: [30], min_length=1, max_length=20)
    aspect: Aspect = "9:16"
    caption_style: CaptionStyle = "default"
    captions: StrictBool = True
    padding: float = Field(0.5, ge=0, le=5, allow_inf_nan=False)
    bgm: StrictBool = False
    duck: StrictBool = True
    bgm_volume: float = Field(0.18, ge=0, le=1, allow_inf_nan=False)
    face_crop: StrictBool = True
    grade: StrictBool = False
    hook_zoom: StrictBool = False
    platform: Literal["", "shorts", "reels", "tiktok", "square", "youtube", "instagram"] = ""
    render_mode: Literal["exact", "target"] = "exact"


class RenderRequest(RenderSettings):
    parent_job: JobId
    highlights: list[HighlightSelection] = Field(default_factory=list, max_length=20)


class TranscriptSegment(BaseModel):
    start: FiniteTime
    end: FiniteTime
    text: str = Field("", max_length=20000)
    speech_score: Signal = 0.5
    emotion_score: Signal = 0.5
    audio_score: Signal = 0.5
    visual_score: Signal = 0.5

    @model_validator(mode="after")
    def check_order(self):
        if self.end <= self.start:
            raise ValueError("Segment end must be after start")
        return self


class HighlightRequest(AnalysisOptions):
    segments: list[TranscriptSegment] = Field(default_factory=list, max_length=2000)


class EditorState(BaseModel):
    selected: list[StrictBool] = Field(default_factory=list, max_length=20)
    trims: list[ClipWindow] = Field(default_factory=list, max_length=20)


class ProjectRequest(BaseModel):
    id: JobId | None = None
    name: str = Field("Untitled", min_length=1, max_length=80)
    job_id: JobId | None = None
    render_job_id: JobId | None = None
    url: str = Field("", max_length=2048)
    notes: str = Field("", max_length=4000)
    settings: RenderSettings = Field(default_factory=RenderSettings)
    analysis: AnalysisOptions = Field(default_factory=AnalysisOptions)
    editor: EditorState = Field(default_factory=EditorState)
