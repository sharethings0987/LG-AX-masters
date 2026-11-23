import random
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, public_data, youth_quiz
from app.main import app
from app.youth_quiz import Character, build_search, fits, normalize, pick_policy

TODAY = date(2026, 11, 23)
SEOUL = "11110,11140"
NATION = ",".join(f"{c}110" for c in youth_quiz.SIDO_NAMES)


def row(no, name, **kw):
    base = {
        "plcyNo": no, "plcyNm": name, "plcyExplnCn": f"{name} 설명", "plcySprtCn": "지원 내용",
        "lclsfNm": "금융･복지･문화", "mclsfNm": "취약계층 및 금융지원", "plcyKywdNm": "보조금",
        "sprtTrgtMinAge": "19", "sprtTrgtMaxAge": "34", "zipCd": NATION,
        "pvsnInstGroupCd": "0054001", "rgtrHghrkInstCdNm": "금융위원회", "sprvsnInstCdNm": "금융위원회 서민금융과",
        "jobCd": "0013010", "mrgSttsCd": "0055003", "earnCndSeCd": "0043001",
        "aplyPrdSeCd": "0057001", "aplyYmd": "20261007 ~ 20261016", "bizPrdEndYmd": "",
        "plcyPvsnMthdCd": "0042006", "aplyUrlAddr": "https://fill4young.kinfa.or.kr/yfs/main", "inqCnt": "100",
    }
    base.update(kw)
    return base


WORKER = Character(age=20, sido="11", employment="employed", married=False)


def test_region_comes_from_institution_not_wrong_nationwide_zip():
    p, = normalize([row("1", "의성 청년공간", pvsnInstGroupCd="0054002", rgtrHghrkInstCdNm="경상북도",
                        sprvsnInstCdNm="경상북도 의성군", aplyUrlAddr="https://www.usc.go.kr")], TODAY)
    assert p.sido == {"47"}
    assert not fits(p, WORKER)


def test_keeps_this_years_closed_round_but_drops_old_or_unusable_policies():
    rows = [
        row("keep", "청년미래적금", earnCndSeCd="0043003", earnEtcCn="총급여 7500만원 이하"),  # 올해 10월 마감분
        row("old", "작년 정책", aplyYmd="20250101 ~ 20250131"),
        row("closed", "마감", aplyPrdSeCd="0057003"),
        row("infra", "인프라", plcyPvsnMthdCd="0042001"),
        row("nourl", "주소 없음", aplyUrlAddr="", refUrlAddr1=""),
        row("private", "사설 주소", aplyUrlAddr="https://example.com/apply"),
        row("special", "자립준비청년 지원"),
    ]
    kept = normalize(rows, TODAY)
    assert [p.no for p in kept] == ["keep"]
    assert "7500만원" in kept[0].extra


def test_bare_official_domain_gets_https():
    p, = normalize([row("1", "청년내일저축계좌", aplyUrlAddr="www.bokjiro.go.kr")], TODAY)
    assert p.url == "https://www.bokjiro.go.kr"


@pytest.mark.parametrize("kw, ok", [
    ({}, True),
    ({"sprtTrgtMinAge": "25"}, False),
    ({"jobCd": "0013003"}, False),             # 미취업자 전용
    ({"jobCd": "0013001,0013004"}, True),      # 재직자 포함
    ({"mrgSttsCd": "0055001"}, False),         # 기혼 전용
    ({"plcyNm": "대학생 학자금 지원"}, False),  # 대학생 전용
])
def test_fits_checks_age_job_marriage_and_student(kw, ok):
    p, = normalize([row("1", kw.pop("plcyNm", "정책"), **kw)], TODAY)
    assert fits(p, WORKER) is ok


def test_student_only_policy_fits_students():
    p, = normalize([row("1", "대학생 학자금 지원")], TODAY)
    assert fits(p, Character(20, "11", "student", False))


def test_search_has_exactly_one_official_result():
    p, = normalize([row("1", "청년미래적금")], TODAY)
    for seed in range(10):
        results = build_search(p, random.Random(seed), TODAY)
        assert len(results) == 4
        assert [r["ok"] for r in results].count(True) == 1
        official = next(r for r in results if r["ok"])
        assert official["url"] == "fill4young.kinfa.or.kr/…"
        kinds = {r["kind"]: r for r in results}
        assert kinds["lookalike"]["url"] == "fill4young.kinfa-or.com"
        assert not kinds["agency"]["url"].endswith((".go.kr", ".or.kr"))
        assert all(r["why"] for r in results)


def test_pick_prefers_policies_aimed_at_the_character_and_avoids_repeats():
    rows = [row(f"n{i}", f"누구나 {i}", inqCnt="10") for i in range(10)]
    rows.append(row("worker", "재직 청년 적금", jobCd="0013001", inqCnt="10"))
    policies = normalize(rows, TODAY)
    picks = {pick_policy(policies, "money", WORKER, random.Random(s))["policy"]["id"] for s in range(40)}
    assert "worker" in picks
    again = pick_policy(policies, "money", WORKER, random.Random(1), frozenset({"worker"}))
    assert again["policy"]["id"] != "worker"
    assert pick_policy(policies, "job", WORKER, random.Random(1)) is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(youth_quiz, "_cache", {"at": 0.0, "policies": None})
    with TestClient(app) as c:
        yield c


def test_quiz_endpoint_downloads_all_pages_once_and_hides_key(client, monkeypatch):
    monkeypatch.setenv("ONTONG_YOUTH_KEY", "youth-server-only-key")
    rows = [row(str(i), f"정책 {i}") for i in range(7)]
    calls = []

    async def fake_fetch(url, params, source):
        calls.append(params)
        page = params["pageNum"]
        return {"resultCode": 200, "result": {"pagging": {"totCount": len(rows)},
                                               "youthPolicyList": rows[(page - 1) * 5: page * 5]}}

    monkeypatch.setattr(youth_quiz, "PAGE_SIZE", 5)
    monkeypatch.setattr(public_data, "_fetch_json", fake_fetch)
    params = {"situation": "money", "age": 20, "sido": "11", "employment": "employed", "seed": 3}
    r = client.get("/api/public/youth-quiz", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["policy"]["name"].startswith("정책")
    assert len(body["results"]) == 4 and body["checks"]
    assert [c["pageNum"] for c in calls] == [1, 2]
    assert all(c["apiKeyNm"] == "youth-server-only-key" for c in calls)
    assert "youth-server-only-key" not in r.text

    assert client.get("/api/public/youth-quiz", params=params).status_code == 200
    assert len(calls) == 2  # 두 번째 요청은 받아 둔 목록을 쓴다


def test_quiz_endpoint_validates_input_and_reports_no_match(client, monkeypatch):
    monkeypatch.setattr(youth_quiz, "_cache", {"at": 1e18, "policies": normalize([row("1", "정책")], TODAY)})
    base = {"situation": "money", "age": 20, "sido": "11", "employment": "employed"}
    assert client.get("/api/public/youth-quiz", params=base).status_code == 200
    assert client.get("/api/public/youth-quiz", params={**base, "sido": "99"}).status_code == 422
    assert client.get("/api/public/youth-quiz", params={**base, "situation": "marry"}).status_code == 422
    assert client.get("/api/public/youth-quiz", params={**base, "age": 40}).status_code == 404


def test_quiz_endpoint_requires_server_key(client, monkeypatch):
    monkeypatch.delenv("ONTONG_YOUTH_KEY", raising=False)
    r = client.get("/api/public/youth-quiz",
                   params={"situation": "money", "age": 20, "sido": "11", "employment": "employed"})
    assert r.status_code == 503


def test_download_retries_a_failed_page(client, monkeypatch):
    monkeypatch.setenv("ONTONG_YOUTH_KEY", "k")
    monkeypatch.setattr(youth_quiz, "RETRY_DELAY", 0)
    rows = [row("1", "정책")]
    attempts = []

    async def flaky(url, params, source):
        attempts.append(params["pageNum"])
        if len(attempts) == 1:
            raise youth_quiz.HTTPException(502, "일시 오류")
        return {"resultCode": 200, "result": {"pagging": {"totCount": 1}, "youthPolicyList": rows}}

    monkeypatch.setattr(public_data, "_fetch_json", flaky)
    r = client.get("/api/public/youth-quiz",
                   params={"situation": "money", "age": 20, "sido": "11", "employment": "employed"})
    assert r.status_code == 200
    assert attempts == [1, 1]
