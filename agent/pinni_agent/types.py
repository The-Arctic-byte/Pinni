"""Core domain models mirroring the contract schemas in contract/schemas/."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

Scale = Literal["area", "city", "finland", "world"]
Category = Literal[
    "economy", "society", "politics", "shopping", "sport", "safety",
    "culture", "transport", "education", "housing", "health", "work",
    "environment", "technology", "world", "cityLife"
]
Need = Literal["safety", "information", "understanding", "usefulness", "community", "emotion"]
Risk = Literal["none", "amber", "red"]
TargetGroup = Literal["student", "worker", "family", "jobSeeker", "local", "retiree", "other"]
StoryStatus = Literal["draft", "inReview", "published", "rejected"]
StoryOrigin = Literal["agent", "community"]
AuditStep = Literal[
    "find", "gather", "select", "locate", "rank", "explain", "translate",
    "check", "route", "review", "publish", "distribute", "moderate", "skip"
]


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Location(BaseModel):
    coordinate: Coordinate
    radiusMeters: float = Field(default=0.0, ge=0)


class ContextCard(BaseModel):
    question: Dict[str, str]
    answer: Dict[str, str]


class ActionPlace(BaseModel):
    name: Dict[str, str]
    coordinate: Optional[Coordinate] = None
    url: Optional[str] = None


class TimelineItem(BaseModel):
    at: str
    text: Dict[str, str]


class Explanation(BaseModel):
    known: Optional[List[Dict[str, str]]] = None
    happened: Optional[Dict[str, str]] = None
    notKnown: Optional[Dict[str, str]] = None
    forYou: Dict[str, str]
    context: Optional[ContextCard] = None
    actionPlace: Optional[ActionPlace] = None
    timeline: Optional[List[TimelineItem]] = None


class OriginalSentence(BaseModel):
    fi: str
    en: str


class Source(BaseModel):
    name: str
    url: Optional[str] = None
    publishedAt: Optional[str] = None


class TranslationTier(BaseModel):
    language: str
    tier: Literal[1, 2, 3]
    reviewedBy: Optional[str] = None


class Verification(BaseModel):
    verifiedBy: str
    verifiedAt: str


class CommunityInfo(BaseModel):
    reportId: str
    confirmations: int = 0


class Story(BaseModel):
    id: str
    status: StoryStatus = "draft"
    origin: StoryOrigin = "agent"
    scale: Scale
    placeId: str
    location: Optional[Location] = None
    category: Category
    tags: List[str] = Field(default_factory=list)
    needs: List[Need] = Field(min_length=1)
    risk: Risk = "none"
    isOpinion: bool = False
    importance: float = Field(ge=0.0, le=1.0, default=0.5)
    affects: List[str] = Field(default_factory=list)
    mapObject: Optional[str] = None
    label: Dict[str, str]
    title: Dict[str, str]
    explanation: Explanation
    originals: Optional[List[OriginalSentence]] = None
    wordOfDay: Optional[Dict[str, Any]] = None
    sources: List[Source] = Field(min_length=1)
    translations: List[TranslationTier] = Field(default_factory=list)
    verification: Optional[Verification] = None
    community: Optional[CommunityInfo] = None
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    publishedAt: Optional[str] = None


class EventContext(BaseModel):
    screen: Optional[Literal["onboarding", "map", "news", "story", "community", "profile", "notification"]] = None
    scale: Optional[Scale] = None
    position: Optional[int] = None


class Event(BaseModel):
    id: str
    userId: str
    type: Literal[
        "onboardingAnswer", "profileEdit",
        "open", "dwell", "skip", "like", "dislike", "notForMe", "reject", "share", "save",
        "followPlace", "unfollowPlace", "joinChannel", "leaveChannel", "postToChannel",
        "report", "flagWrong", "confirm",
        "zoom", "mapTap", "placeChipTap", "notificationOpen"
    ]
    storyId: Optional[str] = None
    channelId: Optional[str] = None
    placeId: Optional[str] = None
    value: Optional[float] = None
    detail: Optional[Dict[str, Any]] = None
    context: Optional[EventContext] = None
    occurredAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HardFilters(BaseModel):
    categories: List[Category] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class ResidenceConsent(BaseModel):
    status: Literal["finnish", "eu", "nonEu"]
    consent: Literal[True]


class HousingConsent(BaseModel):
    provider: Literal["psoas", "other", "none"]
    consent: Literal[True]


class Profile(BaseModel):
    userId: str
    language: str = "en"
    uiLanguage: Optional[Literal["en", "fi", "fa", "sv"]] = "en"
    targetGroups: List[TargetGroup] = Field(default_factory=list)
    homePlaceId: Optional[str] = None
    homeCountryCode: Optional[str] = None
    residence: Optional[ResidenceConsent] = None
    housing: Optional[HousingConsent] = None
    categoryWeights: Dict[str, float] = Field(default_factory=dict)
    interests: List[str] = Field(default_factory=list)
    wantedNews: List[str] = Field(default_factory=list)
    followedPlaceIds: List[str] = Field(default_factory=list)
    hardFilters: HardFilters = Field(default_factory=HardFilters)
    notifications: Optional[Dict[str, bool]] = None
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class FeedItem(BaseModel):
    storyId: str
    relevance: float = Field(ge=0.0, le=1.0)
    mustSee: bool = False
    isExploration: Optional[bool] = False
    reasons: List[Dict[str, str]] = Field(default_factory=list)


class FeedPage(BaseModel):
    userId: str
    generatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scale: Optional[Scale] = None
    placeId: Optional[str] = None
    personalization: float = Field(ge=0.0, le=1.0, default=0.0)
    items: List[FeedItem] = Field(default_factory=list)
    nextCursor: Optional[str] = None


class AuditEntry(BaseModel):
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    actor: str = "agent:supervisor"
    step: AuditStep
    message: str
    storyId: Optional[str] = None
    reportId: Optional[str] = None


class QueueItem(BaseModel):
    kind: Literal["agentDraft", "communityReport", "readerFlag"]
    id: str
    risk: Risk = "none"
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    trail: List[AuditEntry] = Field(default_factory=list)
