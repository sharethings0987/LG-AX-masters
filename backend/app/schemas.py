"""요청·응답 모델과 정책 규칙 검증."""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PlayerId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{8,64}$", description="브라우저에서 만든 익명 ID")]
ShortText = Annotated[str, Field(max_length=40)]

# 게임 상태(G)에서 규칙이 읽을 수 있는 값. 프론트 backend.js의 RF/필드 해석과 짝을 이룬다.
FIELD_RE = re.compile(r"^(age|job|h|employed|tenure|me\.q|st\.(health|mood|soc|self|burn|money)|f\.[a-z][a-z0-9_]{0,23})$")
EFFECT_KEYS = {"money", "health", "mood", "soc", "self", "burn", "prep", "hp"}
NUM_OPS = {"lt", "le", "gt", "ge"}


class Rule(BaseModel):
    """정책 조건 하나. 단일 비교(field+op) 또는 묶음(all / any) 중 하나."""

    model_config = ConfigDict(extra="forbid")

    label: Optional[Annotated[str, Field(min_length=1, max_length=60)]] = None
    field: Optional[str] = None
    op: Optional[Literal["between", "in", "lt", "le", "gt", "ge", "eq", "truthy"]] = None
    value: Any = None
    all: Optional[list[Rule]] = None
    any: Optional[list[Rule]] = None

    @model_validator(mode="after")
    def _shape(self) -> Rule:
        kinds = [self.field is not None or self.op is not None, self.all is not None, self.any is not None]
        if sum(kinds) != 1:
            raise ValueError("규칙은 field+op, all, any 중 정확히 하나만 가져야 합니다")
        group = self.all if self.all is not None else self.any
        if group is not None:
            if not group:
                raise ValueError("all/any는 비어 있을 수 없습니다")
            return self
        if not self.field or not FIELD_RE.match(self.field):
            raise ValueError(f"알 수 없는 field: {self.field!r}")
        if self.op is None:
            raise ValueError("op가 필요합니다")
        v = self.value
        is_num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
        if self.op == "between" and not (isinstance(v, list) and len(v) == 2 and all(map(is_num, v)) and v[0] <= v[1]):
            raise ValueError("between의 value는 [최소, 최대] 숫자 쌍이어야 합니다")
        if self.op == "in" and not (isinstance(v, list) and v):
            raise ValueError("in의 value는 비어 있지 않은 배열이어야 합니다")
        if self.op in NUM_OPS and not is_num(v):
            raise ValueError(f"{self.op}의 value는 숫자여야 합니다")
        if self.op == "truthy" and v is not None:
            raise ValueError("truthy에는 value를 넣지 않습니다")
        return self


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=60)]
    site: Annotated[str, Field(min_length=1, max_length=20)]
    hint: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(min_length=1, max_length=300)]
    requirements: Annotated[list[Rule], Field(min_length=1, max_length=10)]
    effects: dict[str, Annotated[int, Field(ge=-50, le=50)]]
    active: bool = True
    sort_order: Optional[int] = None

    @field_validator("requirements")
    @classmethod
    def _top_level_labels(cls, v: list[Rule]) -> list[Rule]:
        # 화면의 「나는 대상일까?」 목록에 그대로 보이므로 최상위 규칙엔 설명이 꼭 있어야 한다.
        if any(not r.label for r in v):
            raise ValueError("최상위 규칙마다 label이 필요합니다")
        return v

    @field_validator("effects")
    @classmethod
    def _effect_keys(cls, v: dict[str, int]) -> dict[str, int]:
        bad = set(v) - EFFECT_KEYS
        if bad:
            raise ValueError(f"알 수 없는 효과 키: {sorted(bad)}")
        return v


class PolicyOut(BaseModel):
    key: str
    name: str
    site: str
    hint: str
    description: str
    requirements: list[dict]
    effects: dict[str, int]
    active: bool
    sort_order: int
    updated_at: str


class PolicyCatalog(BaseModel):
    sites: dict[str, str]
    policies: list[PolicyOut]


class LetterIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    player_id: PlayerId
    to: Annotated[str, Field(min_length=1, max_length=50)]
    text: Annotated[str, Field(min_length=1, max_length=400)]
    play_id: Optional[int] = None


class LetterOut(BaseModel):
    id: int
    to: str
    text: str
    play_id: Optional[int]
    created_at: str


class Character(BaseModel):
    name: ShortText
    region: ShortText
    family: Annotated[int, Field(ge=1, le=5)]
    path: ShortText


class Result(BaseModel):
    job: ShortText
    house: ShortText
    stats: dict[Literal["health", "mood", "soc", "self", "burn", "money"], float]
    cash: int
    debt: int
    partner: bool = False
    married: bool = False
    kid: bool = False
    pet: bool = False


class YearEntry(BaseModel):
    age: Annotated[int, Field(ge=18, le=45)]
    mood: float
    text: Annotated[str, Field(max_length=300)]


KeyList = Annotated[list[Annotated[str, Field(max_length=32)]], Field(max_length=100)]


class PlayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: PlayerId
    variant: Literal["A", "B", "C"]
    mode: Literal["other", "my"]
    care: Optional[ShortText] = None
    auto: bool = False
    character: Character
    result: Result
    eligible: KeyList = []
    done: KeyList = []
    missed: KeyList = []
    heard: KeyList = []
    year_map: Annotated[list[YearEntry], Field(max_length=25)] = []


class PlayPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_id: PlayerId
    goal_answer: Optional[Annotated[str, Field(max_length=30)]] = None
    thanks_answer: Optional[Annotated[str, Field(max_length=30)]] = None


class PlayCreated(BaseModel):
    id: int
    created_at: str


class PlaySummary(BaseModel):
    id: int
    variant: str
    mode: str
    character: Character
    result: Result
    done: list[str]
    eligible: list[str]
    goal_answer: Optional[str]
    thanks_answer: Optional[str]
    created_at: str
