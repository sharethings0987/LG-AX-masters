"""Server-side proxies for public benefit, LH housing notice and youth policy APIs."""
from __future__ import annotations

import logging
import os
import re
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Path as PathParam, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public", tags=["public-data"])

GOV24_BASE_URL = "https://api.odcloud.kr/api/gov24/v3"
LH_URL = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
YOUTH_POLICY_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
YOUTH_SOURCE = "온통청년 청년정책"


def _upstream_error_code(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        envelope = payload.get("OpenAPI_ServiceResponse", payload)
        if isinstance(envelope, dict):
            header = envelope.get("cmmMsgHeader", envelope)
            if isinstance(header, dict):
                for name in ("errMsg", "returnAuthMsg", "returnReasonCode"):
                    value = header.get(name)
                    if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
                        return value

    for name in ("errMsg", "returnAuthMsg", "returnReasonCode"):
        match = re.search(rf"<{name}>\s*([A-Za-z0-9_.-]{{1,80}})\s*</{name}>", response.text)
        if match:
            return match.group(1)
    return None


def _service_key(name: str, label: str) -> str:
    key = os.environ.get(name, "").strip()
    if not key:
        raise HTTPException(503, f"{label} API 인증키가 서버에 설정되지 않았습니다.")
    return key


async def _fetch_json(url: str, params: dict[str, str | int], source: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        error_code = _upstream_error_code(exc.response)
        logger.warning(
            "%s upstream returned HTTP %s%s",
            source,
            exc.response.status_code,
            f" ({error_code})" if error_code else "",
        )
        detail = f"{source} API 요청이 실패했습니다 (HTTP {exc.response.status_code}). "
        if error_code:
            detail += f"오류 코드: {error_code}. "
        raise HTTPException(
            502,
            detail + "인증키와 활용 신청 상태를 확인해 주세요.",
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("%s upstream request failed: %s", source, type(exc).__name__)
        raise HTTPException(502, f"{source} API에 연결할 수 없습니다.") from exc
    except ValueError as exc:
        logger.warning("%s upstream returned invalid JSON", source)
        raise HTTPException(502, f"{source} API 응답을 읽을 수 없습니다.") from exc


@router.get("/benefits")
async def list_benefits(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    key = _service_key("GOV24_SERVICE_KEY", "정부24 공공서비스")
    return await _fetch_json(
        f"{GOV24_BASE_URL}/serviceList",
        {"serviceKey": key, "perPage": per_page, "page": page, "returnType": "JSON"},
        "정부24 공공서비스",
    )


@router.get("/benefits/{service_id}/conditions")
async def benefit_conditions(
    service_id: str = PathParam(..., min_length=1, max_length=64),
    page: int = Query(1, ge=1),
    per_page: int = Query(100, ge=1, le=100),
):
    key = _service_key("GOV24_SERVICE_KEY", "정부24 공공서비스")
    return await _fetch_json(
        f"{GOV24_BASE_URL}/supportConditions",
        {
            "serviceKey": key,
            "cond[서비스ID::EQ]": service_id,
            "perPage": per_page,
            "page": page,
            "returnType": "JSON",
        },
        "정부24 공공서비스",
    )


@router.get("/lh-notices")
async def list_lh_notices(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    key = _service_key("LH_SERVICE_KEY", "LH 임대공고")
    start = start_date or date.today() - timedelta(days=30)
    end = end_date or date.today() + timedelta(days=365)
    if end < start:
        raise HTTPException(422, "종료일은 시작일보다 빠를 수 없습니다.")

    return await _fetch_json(
        LH_URL,
        {
            "serviceKey": key,
            "PG_SZ": per_page,
            "PAGE": page,
            "UPP_AIS_TP_CD": "06",
            "PAN_NT_ST_DT": start.strftime("%Y.%m.%d"),
            "CLSG_DT": end.strftime("%Y.%m.%d"),
        },
        "LH 임대공고",
    )


def _youth_result(payload: Any) -> Any:
    """온통청년은 오류도 HTTP 200으로 줄 수 있어 resultCode와 result를 확인한다."""
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return payload
    code = payload.get("resultCode") if isinstance(payload, dict) else None
    code = str(code) if code is not None else ""
    logger.warning("%s upstream returned no result (resultCode=%s)", YOUTH_SOURCE, code or "-")
    detail = f"{YOUTH_SOURCE} API가 결과를 돌려주지 않았습니다. "
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        detail += f"오류 코드: {code}. "
    raise HTTPException(502, detail + "인증키와 활용 신청 상태를 확인해 주세요.")


@router.get("/youth-policies")
async def list_youth_policies(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None, max_length=100),
    name: str | None = Query(None, max_length=100),
):
    key = _service_key("ONTONG_YOUTH_KEY", YOUTH_SOURCE)
    params: dict[str, str | int] = {
        "apiKeyNm": key,
        "pageNum": page,
        "pageSize": per_page,
        "pageType": "1",
        "rtnType": "json",
    }
    if keyword and keyword.strip():
        params["plcyKywdNm"] = keyword.strip()
    if name and name.strip():
        params["plcyNm"] = name.strip()
    return _youth_result(await _fetch_json(YOUTH_POLICY_URL, params, YOUTH_SOURCE))


@router.get("/youth-policies/{policy_no}")
async def youth_policy_detail(
    policy_no: str = PathParam(..., pattern=r"^[A-Za-z0-9_-]{1,40}$"),
):
    key = _service_key("ONTONG_YOUTH_KEY", YOUTH_SOURCE)
    return _youth_result(await _fetch_json(
        YOUTH_POLICY_URL,
        {"apiKeyNm": key, "pageType": "2", "plcyNo": policy_no, "rtnType": "json"},
        YOUTH_SOURCE,
    ))
