"""온통청년 청년정책으로 게임 속 「진짜 공식 안내 찾기」 문제를 만든다.

캐릭터 상황(나이·지역·취업상태·결혼)에 맞는 실제 정책 하나를 고르고, 검색 결과 4개를 만든다.
진짜는 정책의 공식 신청·안내 주소 하나뿐이고, 나머지는 대행업체·가짜(유사) 주소·오래된 후기다.
"""
from __future__ import annotations

import asyncio
import math
import random
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query

from . import public_data

router = APIRouter(prefix="/api/public", tags=["public-data"])

CACHE_TTL = 12 * 60 * 60  # 정책 전체 목록을 다시 받는 주기(초)
PAGE_SIZE = 100
MAX_PAGES = 80
RETRIES = 2
RETRY_DELAY = 1.0  # 초

# 시도 코드(법정동 앞 2자리) → 이름. 온통청년 데이터는 광주·전남을 12(전남광주통합특별시)로 쓴다.
SIDO_NAMES = {
    "11": "서울특별시", "12": "전남광주통합특별시", "26": "부산광역시", "27": "대구광역시",
    "28": "인천광역시", "30": "대전광역시", "31": "울산광역시", "36": "세종특별자치시",
    "41": "경기도", "43": "충청북도", "44": "충청남도", "47": "경상북도", "48": "경상남도",
    "50": "제주특별자치도", "51": "강원특별자치도", "52": "전북특별자치도",
}
ALL_SIDO = frozenset(SIDO_NAMES)
# 기관 이름의 앞부분으로 시도를 찾는다. 지역 코드(zipCd)에 전국이 잘못 들어간 지자체 정책이 있어서다.
SIDO_PREFIXES = [
    ("서울", "11"), ("부산", "26"), ("대구", "27"), ("인천", "28"), ("대전", "30"), ("울산", "31"),
    ("세종", "36"), ("경기", "41"), ("강원", "51"), ("충청북도", "43"), ("충북", "43"),
    ("충청남도", "44"), ("충남", "44"), ("전북", "52"), ("전라북도", "52"), ("전남광주", "12"),
    ("전라남도", "12"), ("전남", "12"), ("광주광역시", "12"), ("광주시청", "12"),
    ("경상북도", "47"), ("경북", "47"), ("경상남도", "48"), ("경남", "48"), ("제주", "50"),
]

JOB_ANY = "0013010"
EMPLOYMENT_CODES = {
    "unemployed": "0013003",  # 미취업자
    "employed": "0013001",    # 재직자
    "freelancer": "0013004",  # 프리랜서
    "founder": "0013006",     # (예비)창업자
    "student": "0013003",     # 대학생(미취업자로 판정)
}
STUDENT_ONLY = re.compile(r"대학생|대학교|재학생|학자금|대학 재학")
JOB_LABELS = {
    "0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서",
    "0013005": "일용근로자", "0013006": "(예비)창업자", "0013007": "단기근로자",
    "0013008": "영농종사자", "0013009": "기타",
}
MARRIED, SINGLE = "0055001", "0055002"
NO_TEXT = {"", "-", "해당없음", "해당 없음", "없음", "제한없음", "제한 없음", "무관"}
# 신청해서 받는 혜택이 아닌 정책(인프라 구축·경제적 규제)은 문제에 쓰지 않는다.
SKIP_PROVISION = {"0042001", "0042012"}
# 이름·설명에만 적힌 특정 대상 조건. 일반 캐릭터에게 권하기 어려운 정책은 고르지 않는다.
SPECIAL_TARGET = re.compile(
    r"자립준비|보호종료|퇴소|장애|북한이탈|탈북|다문화|한부모|기초생활|수급자|차상위|"
    r"농업인|영농|농업|어업|어촌|수산|군인|장병|제대|전역|예술인|외국인|유학생|고교|고등학"
)
# 공식 주소로 인정하는 도메인. 가짜 주소와 구별하는 법을 배우는 문제라 공공 도메인만 쓴다.
OFFICIAL_SUFFIXES = (".go.kr", ".or.kr")

Situation = Literal["job", "house", "money"]
SITUATION_LABELS = {"job": "취업", "house": "주거", "money": "금융·자산"}


@dataclass
class Policy:
    no: str
    name: str
    org: str
    summary: str
    support: str
    extra: str
    url: str
    apply_period: str
    views: int
    min_age: int
    max_age: int
    sido: frozenset[str]
    jobs: frozenset[str]
    marriage: str
    tags: frozenset[str]
    student_only: bool = False


def _s(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    return str(value).strip() if value is not None else ""


def _int(text: str) -> int:
    return int(text) if text.isdigit() else 0


def _sido_from_name(*names: str) -> str | None:
    for name in names:
        for prefix, code in SIDO_PREFIXES:
            if name.startswith(prefix):
                return code
    return None


def _policy_sido(row: dict[str, Any]) -> frozenset[str] | None:
    """정책 대상 시도. 알 수 없으면 None(문제에 쓰지 않음)."""
    zips = frozenset(z.strip()[:2] for z in _s(row, "zipCd").split(",") if z.strip()[:2] in ALL_SIDO)
    if _s(row, "pvsnInstGroupCd") == "0054001":  # 중앙부처
        return zips or ALL_SIDO
    named = _sido_from_name(
        _s(row, "rgtrHghrkInstCdNm"), _s(row, "rgtrUpInstCdNm"),
        _s(row, "sprvsnInstCdNm"), _s(row, "rgtrInstCdNm"),
    )
    if named:
        return frozenset({named})
    return zips if len(zips) == 1 else None


def _is_current(row: dict[str, Any], cutoff: str) -> bool:
    """올해 운영하는 정책인가. 해마다 열리는 정책이 많아 올해 신청 기간이 지난 것도 남긴다."""
    if _s(row, "aplyPrdSeCd") == "0057003":  # 마감
        return False
    period = _s(row, "aplyYmd")
    if "~" in period:
        end = re.sub(r"\D", "", period.split("~")[-1])[:8]
        if len(end) == 8 and end < cutoff:
            return False
    biz_end = _s(row, "bizPrdEndYmd")
    return not (len(biz_end) == 8 and biz_end.isdigit() and biz_end < cutoff)


def _tags(row: dict[str, Any]) -> frozenset[str]:
    mclsf, lclsf, kywd = _s(row, "mclsfNm"), _s(row, "lclsfNm"), _s(row, "plcyKywdNm")
    tags = set()
    if "취업" in mclsf or "장기미취업청년" in kywd:
        tags.add("job")
    if lclsf == "주거" or "주거지원" in kywd:
        tags.add("house")
    if mclsf.startswith("취약계층") or "대출" in kywd or "금리혜택" in kywd:
        tags.add("money")
    return frozenset(tags)


def _clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _official_url(row: dict[str, Any]) -> str:
    for key in ("aplyUrlAddr", "refUrlAddr1", "refUrlAddr2"):
        url = _s(row, key)
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        host = (urlparse(url).hostname or "").lower()
        if url.startswith("https://") and host.endswith(OFFICIAL_SUFFIXES):
            return url
    return ""


def _extra_conditions(row: dict[str, Any]) -> str:
    parts = [_s(row, k) for k in ("earnEtcCn", "addAplyQlfcCndCn", "ptcpPrpTrgtCn")]
    return _clip(" / ".join(p for p in parts if p not in NO_TEXT), 220)


def normalize(rows: list[dict[str, Any]], today: date | None = None) -> list[Policy]:
    cutoff = f"{(today or date.today()).year}0101"
    out = []
    for row in rows:
        tags = _tags(row)
        sido = _policy_sido(row)
        url = _official_url(row)
        text = _s(row, "plcyNm") + " " + _s(row, "plcyExplnCn")
        if (not tags or sido is None or not url or not _s(row, "plcyNo")
                or not _is_current(row, cutoff) or _s(row, "plcyPvsnMthdCd") in SKIP_PROVISION
                or SPECIAL_TARGET.search(text)):
            continue
        out.append(Policy(
            no=_s(row, "plcyNo"),
            name=_clip(_s(row, "plcyNm"), 60),
            org=_clip(_s(row, "sprvsnInstCdNm") or _s(row, "operInstCdNm"), 40),
            summary=_clip(_s(row, "plcyExplnCn"), 160),
            support=_clip(_s(row, "plcySprtCn"), 300),
            extra=_extra_conditions(row),
            url=url,
            apply_period=_s(row, "aplyYmd") or ("상시" if _s(row, "aplyPrdSeCd") == "0057002" else ""),
            views=_int(_s(row, "inqCnt")),
            min_age=_int(_s(row, "sprtTrgtMinAge")),
            max_age=_int(_s(row, "sprtTrgtMaxAge")),
            sido=sido,
            jobs=frozenset(c.strip() for c in _s(row, "jobCd").split(",") if c.strip()) or frozenset({JOB_ANY}),
            marriage=_s(row, "mrgSttsCd"),
            tags=tags,
            student_only=bool(STUDENT_ONLY.search(text)),
        ))
    return out


# ---------------------------------------------------------------- 판정

@dataclass(frozen=True)
class Character:
    age: int
    sido: str
    employment: str
    married: bool


def _age_text(p: Policy) -> str:
    if p.min_age and p.max_age:
        return f"만 {p.min_age}세" if p.min_age == p.max_age else f"만 {p.min_age}~{p.max_age}세"
    if p.max_age:
        return f"만 {p.max_age}세 이하"
    if p.min_age:
        return f"만 {p.min_age}세 이상"
    return "나이 제한 없음"


def _region_text(p: Policy) -> str:
    if p.sido == ALL_SIDO:
        return "전국"
    if len(p.sido) >= 10:
        return "전국(" + "·".join(SIDO_NAMES[c] for c in sorted(ALL_SIDO - p.sido)) + " 제외)"
    return "·".join(SIDO_NAMES[c] for c in sorted(p.sido))


def _job_text(p: Policy) -> str:
    labels = [JOB_LABELS.get(c, "기타") for c in sorted(p.jobs)]
    named = [x for x in labels if x != "기타"]
    return "·".join(named or labels)


def _target_text(p: Policy) -> str:
    parts = []
    if JOB_ANY not in p.jobs:
        parts.append(_job_text(p))
    if p.marriage == MARRIED:
        parts.append("기혼")
    elif p.marriage == SINGLE:
        parts.append("미혼")
    return " · ".join(parts) or "누구나"


def fits(p: Policy, ch: Character) -> bool:
    """나이·지역·취업상태·결혼 조건이 모두 맞는가."""
    if (p.min_age and ch.age < p.min_age) or (p.max_age and ch.age > p.max_age):
        return False
    if ch.sido not in p.sido:
        return False
    if p.student_only and ch.employment != "student":
        return False
    if JOB_ANY not in p.jobs and EMPLOYMENT_CODES[ch.employment] not in p.jobs:
        return False
    if (p.marriage == MARRIED and not ch.married) or (p.marriage == SINGLE and ch.married):
        return False
    return True


def checks(p: Policy, ch: Character) -> list[str]:
    """결과 화면의 「나는 대상일까?」 목록."""
    employment = {"unemployed": "미취업", "employed": "재직 중", "freelancer": "프리랜서", "founder": "창업",
                  "student": "대학생"}
    out = [f"나이: {_age_text(p)} (지금 만 {ch.age}세)", f"지역: {_region_text(p)} (지금 {SIDO_NAMES[ch.sido]})"]
    if JOB_ANY not in p.jobs:
        out.append(f"대상: {_job_text(p)} (지금 {employment[ch.employment]})")
    if p.marriage in (MARRIED, SINGLE):
        out.append(f"결혼: {'기혼' if p.marriage == MARRIED else '미혼'} (지금 {'기혼' if ch.married else '미혼'})")
    return out


def _score(p: Policy, ch: Character) -> float:
    """캐릭터에게 더 「딱 맞는」 정책일수록 크다: 지금 상태를 콕 집은 정책, 우리 지역 정책, 많이 찾는 정책."""
    s = math.log10(p.views + 10)
    if JOB_ANY not in p.jobs:
        s += 1.5
    if p.sido != ALL_SIDO:
        s += 0.5
    if p.min_age or p.max_age:
        s += 0.3
    return s


# ---------------------------------------------------------------- 검색 결과(보기) 만들기

AGENCY_HOSTS = ["www.quick-jiwon.co.kr", "www.easy-sincheong.com", "www.jiwon-daehaeng.kr", "www.help-youth24.com"]
AGENCY_TITLES = ["{n} 100% 받는 법! 서류 대행해 드립니다", "{n} 대신 신청해 드려요 (승인률 99%)", "{n} 놓치면 손해! 1:1 신청 대행"]
AGENCY_SNIPPETS = ["복잡한 신청, 수수료 30%만 내시면 전부 대신 처리.", "선입금 확인 후 당일 접수! 지금 상담 신청하세요.",
                   "공무원 출신 상담사가 대신 신청해 드립니다. 착수금 5만원."]
FAKE_TITLES = ["{n} 공식 신청 페이지", "{n} 신청하기 | 공식", "[공식] {n} 온라인 접수"]
FAKE_SNIPPETS = ["본인인증 후 바로 신청 완료. 지금 신청하세요.", "계좌번호와 비밀번호를 입력하면 즉시 접수됩니다.",
                 "마감 임박! 지금 바로 본인인증하고 신청하세요."]
BLOG_HOSTS = ["blog.ilsang-log.net", "blog.moneytalk-life.com", "story.saeng-hwal.kr"]
BLOG_TITLES = ["[{y} 후기] {n} 받은 썰 (조건 정리)", "{n} 직접 받아본 후기 ({y})", "[{y}] {n} 신청 방법 총정리"]
BLOG_SNIPPETS = ["제가 받을 땐 이랬어요~ 지금도 똑같을 거예요!", "조건 별거 없어요ㅎㅎ 저는 그냥 됐어요.",
                 "금액이랑 기간은 제 때 기준이에요. 아마 비슷할걸요?"]


def _display(url: str) -> str:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    return host + ("/…" if u.path.strip("/") or u.query else "")


def _lookalike(host: str) -> str:
    for suffix in OFFICIAL_SUFFIXES:
        if host.endswith(suffix):
            return host[: -len(suffix)] + "-" + suffix.strip(".").split(".")[0] + ".com"
    return host + ".kr-apply.com"


def build_search(p: Policy, rng: random.Random, today: date | None = None) -> list[dict[str, Any]]:
    host = (urlparse(p.url).hostname or "").lower()
    site = p.org.split()[0] if p.org else "공식 안내"
    old = (today or date.today()).year - rng.randint(3, 8)
    results = [
        {"kind": "official", "url": _display(p.url), "title": f"{p.name} | {site}",
         "snippet": p.summary or "공식 신청·자격 안내", "ok": True,
         "why": f"공공기관 공식 주소({host})다. 신청 자격과 기간은 여기서 확인하면 된다."},
        {"kind": "agency", "url": rng.choice(AGENCY_HOSTS), "title": rng.choice(AGENCY_TITLES).format(n=p.name),
         "snippet": rng.choice(AGENCY_SNIPPETS), "ok": False,
         "why": "공공기관 주소가 아니고 대행 수수료를 요구한다. 정부 지원 신청에는 수수료가 없다."},
        {"kind": "lookalike", "url": _lookalike(host), "title": rng.choice(FAKE_TITLES).format(n=p.name),
         "snippet": rng.choice(FAKE_SNIPPETS), "ok": False,
         "why": f"진짜 주소({host})를 흉내 낸 가짜 사이트다. 공공기관 주소는 .go.kr·.or.kr로 끝난다."},
        {"kind": "blog", "url": f"{rng.choice(BLOG_HOSTS)}/{old}/…", "title": rng.choice(BLOG_TITLES).format(n=p.name, y=old),
         "snippet": rng.choice(BLOG_SNIPPETS), "ok": False,
         "why": "오래된 개인 후기라 지금의 대상·금액·기간과 다를 수 있다."},
    ]
    rng.shuffle(results)
    return results


def pick_policy(
    policies: list[Policy], situation: str, ch: Character, rng: random.Random,
    exclude: frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
    pool = [p for p in policies if situation in p.tags and fits(p, ch)]
    # 이미 나온 정책은 번호뿐 아니라 이름이 같은 다른 지역판도 빼 둔다.
    seen_names = {p.name for p in policies if p.no in exclude}
    fresh = [p for p in pool if p.no not in exclude and p.name not in seen_names]
    pool = fresh or pool
    if not pool:
        return None
    # 점수가 높은 정책 몇 개 중에서 고른다(매번 같은 정책만 나오지 않게).
    pool.sort(key=lambda p: _score(p, ch), reverse=True)
    p = rng.choice(pool[:8])
    return {
        "situation": situation,
        "situation_label": SITUATION_LABELS[situation],
        "policy": {
            "id": p.no, "name": p.name, "org": p.org, "summary": p.summary, "support": p.support,
            "extra": p.extra, "age": _age_text(p), "region": _region_text(p), "target": _target_text(p),
            "apply_period": p.apply_period, "url": p.url,
        },
        "checks": checks(p, ch),
        "results": build_search(p, rng),
    }


# ---------------------------------------------------------------- 정책 목록 캐시

_cache: dict[str, Any] = {"at": 0.0, "policies": None}
_lock = asyncio.Lock()


async def _fetch_page(key: str, page: int) -> dict[str, Any]:
    """한 페이지를 받는다. 온통청년이 가끔 한 페이지씩 실패해서 몇 번 다시 시도한다."""
    for attempt in range(RETRIES + 1):
        try:
            return public_data._youth_result(await public_data._fetch_json(
                public_data.YOUTH_POLICY_URL,
                {"apiKeyNm": key, "pageNum": page, "pageSize": PAGE_SIZE, "pageType": "1", "rtnType": "json"},
                public_data.YOUTH_SOURCE,
            ))
        except HTTPException as exc:
            if exc.status_code == 503 or attempt == RETRIES:
                raise
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))
    raise AssertionError("unreachable")


async def _download_all() -> list[dict[str, Any]]:
    key = public_data._service_key("ONTONG_YOUTH_KEY", public_data.YOUTH_SOURCE)
    rows: list[dict[str, Any]] = []
    for page in range(1, MAX_PAGES + 1):
        payload = await _fetch_page(key, page)
        result = payload["result"]
        batch = result.get("youthPolicyList") or []
        rows.extend(r for r in batch if isinstance(r, dict))
        total = (result.get("pagging") or {}).get("totCount") or 0
        if not batch or len(rows) >= int(total):
            break
    return rows


async def get_policies() -> list[Policy]:
    if _cache["policies"] is not None and time.monotonic() - _cache["at"] < CACHE_TTL:
        return _cache["policies"]
    async with _lock:
        if _cache["policies"] is not None and time.monotonic() - _cache["at"] < CACHE_TTL:
            return _cache["policies"]
        try:
            policies = normalize(await _download_all())
        except HTTPException:
            if _cache["policies"] is not None:  # 받아 둔 목록이 있으면 오래됐어도 쓴다.
                return _cache["policies"]
            raise
        _cache.update(at=time.monotonic(), policies=policies)
        return policies


@router.get("/youth-quiz")
async def youth_quiz(
    situation: Situation = Query(..., description="job(취업) · house(주거) · money(금융·자산)"),
    age: int = Query(..., ge=15, le=45),
    sido: str = Query(..., pattern=r"^\d{2}$", description="시도 코드 2자리 (예: 11 서울, 41 경기)"),
    employment: Literal["unemployed", "employed", "freelancer", "founder", "student"] = Query(...),
    married: bool = Query(False),
    exclude: str = Query("", max_length=4000, description="이미 나온 정책 번호나 이름(쉼표로 구분)"),
    seed: int | None = Query(None, description="같은 문제를 다시 만들 때 쓰는 값(테스트용)"),
):
    if sido not in ALL_SIDO:
        raise HTTPException(422, "알 수 없는 시도 코드입니다.")
    policies = await get_policies()
    skip = frozenset(x.strip() for x in exclude.split(",") if x.strip())
    quiz = pick_policy(policies, situation, Character(age, sido, employment, married), random.Random(seed), skip)
    if quiz is None:
        raise HTTPException(404, "지금 상황에 맞는 정책을 찾지 못했습니다.")
    return quiz
