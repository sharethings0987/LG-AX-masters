import pytest
from fastapi.testclient import TestClient

from app import db, public_data
from app.main import app
from app.schemas import PolicyIn

PID = "test-player-0001"
OTHER = "someone-else-0002"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    with TestClient(app) as c:  # with 블록이 lifespan(init_db + 시드)을 실행한다
        yield c


def play_body(**over):
    body = {
        "player_id": PID, "variant": "A", "mode": "other", "auto": False,
        "character": {"name": "지원", "region": "서울", "family": 3, "path": "대학생"},
        "result": {"job": "공무원", "house": "전세",
                   "stats": {"health": 70, "mood": 61, "soc": 55, "self": 52, "burn": 30, "money": 48},
                   "cash": 1200, "debt": 300, "married": True},
        "eligible": ["scholar", "npc", "mind"], "done": ["scholar"], "missed": ["mind"], "heard": ["scholar", "mind"],
        "year_map": [{"age": 20, "mood": 58.2, "text": "시험 끝나고 치킨을 먹었다."}],
    }
    body.update(over)
    return body


def test_seed_file_is_valid():
    data = db.load_seed()
    keys = [p["key"] for p in data["policies"]]
    assert len(keys) == len(set(keys)) == 26
    for p in data["policies"]:
        assert p["site"] in data["sites"]
        PolicyIn.model_validate({k: v for k, v in p.items() if k != "key"})


def test_policies_seeded(client):
    r = client.get("/api/policies")
    assert r.status_code == 200
    d = r.json()
    assert d["sites"]["복지로"] == "bokjiro.go.kr"
    assert [p["key"] for p in d["policies"]][:3] == ["scholar", "career", "npc"]
    challenge = next(p for p in d["policies"] if p["key"] == "challenge")
    assert challenge["requirements"][2]["any"][0] == {"field": "st.self", "op": "lt", "value": 50}


def test_admin_api_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("AL_ADMIN_TOKEN", raising=False)
    r = client.put("/api/policies/scholar", json={})
    assert r.status_code == 403


def test_admin_upsert_and_deactivate(client, monkeypatch):
    monkeypatch.setenv("AL_ADMIN_TOKEN", "secret")
    new = {
        "name": "테스트 정책", "site": "복지로", "hint": "이런 게 있대.", "description": "설명",
        "requirements": [{"label": "만 20~30세", "field": "age", "op": "between", "value": [20, 30]}],
        "effects": {"money": 5},
    }
    assert client.put("/api/policies/testpol", json=new).status_code == 401
    r = client.put("/api/policies/testpol", json=new, headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200, r.text
    assert r.json()["sort_order"] == 26
    assert "testpol" in [p["key"] for p in client.get("/api/policies").json()["policies"]]

    r = client.put("/api/policies/testpol", json={**new, "active": False}, headers={"X-Admin-Token": "secret"})
    assert r.status_code == 200
    assert "testpol" not in [p["key"] for p in client.get("/api/policies").json()["policies"]]


@pytest.mark.parametrize("rule", [
    {"label": "x", "field": "age", "op": "between", "value": [30, 20]},
    {"label": "x", "field": "__proto__", "op": "truthy"},
    {"label": "x", "field": "age", "op": "lt", "value": "20"},
    {"label": "x", "all": []},
    {"label": "x", "field": "age", "op": "lt", "value": 3, "any": [{"field": "age", "op": "lt", "value": 1}]},
    {"field": "age", "op": "lt", "value": 3},
])
def test_bad_rules_rejected(client, monkeypatch, rule):
    monkeypatch.setenv("AL_ADMIN_TOKEN", "secret")
    body = {"name": "n", "site": "복지로", "hint": "h", "description": "d", "requirements": [rule], "effects": {}}
    r = client.put("/api/policies/badpol", json=body, headers={"X-Admin-Token": "secret"})
    assert r.status_code == 422


def test_letters_roundtrip(client):
    r = client.post("/api/letters", json={"player_id": PID, "to": "5년 뒤의 나에게", "text": "  네 속도로 가도 돼.  "})
    assert r.status_code == 201
    assert r.json()["text"] == "네 속도로 가도 돼."
    client.post("/api/letters", json={"player_id": OTHER, "to": "남", "text": "남의 편지"})
    got = client.get("/api/letters", params={"player_id": PID}).json()
    assert [l["text"] for l in got] == ["네 속도로 가도 돼."]


def test_letter_validation(client):
    assert client.post("/api/letters", json={"player_id": PID, "to": "a", "text": "x" * 401}).status_code == 422
    assert client.post("/api/letters", json={"player_id": "bad id!", "to": "a", "text": "x"}).status_code == 422


def test_letter_not_linked_to_foreign_play(client):
    play_id = client.post("/api/plays", json=play_body(player_id=OTHER)).json()["id"]
    r = client.post("/api/letters", json={"player_id": PID, "to": "a", "text": "x", "play_id": play_id})
    assert r.json()["play_id"] is None


def test_play_create_patch_list(client):
    r = client.post("/api/plays", json=play_body())
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    assert client.patch(f"/api/plays/{pid}", json={"player_id": OTHER, "goal_answer": "이뤘다"}).status_code == 404
    assert client.patch(f"/api/plays/{pid}", json={"player_id": PID, "goal_answer": "이뤘다"}).status_code == 200
    assert client.patch(f"/api/plays/{pid}", json={"player_id": PID, "thanks_answer": "사람"}).status_code == 200

    plays = client.get("/api/plays", params={"player_id": PID}).json()
    assert len(plays) == 1
    assert plays[0]["goal_answer"] == "이뤘다"  # 두 번째 PATCH가 첫 번째 답을 지우지 않는다
    assert plays[0]["thanks_answer"] == "사람"
    assert plays[0]["result"]["married"] is True


def test_stats(client):
    client.post("/api/plays", json=play_body())
    client.post("/api/plays", json=play_body(variant="B", done=["scholar", "npc"]))
    s = client.get("/api/stats").json()
    assert s["total_plays"] == 2
    assert {v["variant"]: v["plays"] for v in s["by_variant"]} == {"A": 1, "B": 1}
    npc = next(p for p in s["policies"] if p["key"] == "npc")
    assert (npc["eligible"], npc["done"], npc["take_up_rate"]) == (2, 1, 0.5)
    assert next(p for p in s["policies"] if p["key"] == "birth")["take_up_rate"] is None


def test_root_redirects_to_a_variant(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] in {f"/another_life_v8{v}.html" for v in "ABC"}
    assert client.get(r.headers["location"]).status_code == 200


def test_public_benefits_requires_server_key(client, monkeypatch):
    monkeypatch.delenv("GOV24_SERVICE_KEY", raising=False)
    r = client.get("/api/public/benefits")
    assert r.status_code == 503
    assert "인증키" in r.json()["detail"]


def test_public_benefits_proxy_uses_server_key(client, monkeypatch):
    monkeypatch.setenv("GOV24_SERVICE_KEY", "server-only-key")
    captured = {}

    async def fake_fetch(url, params, source):
        captured.update(url=url, params=params, source=source)
        return {"data": [{"서비스명": "테스트 혜택"}]}

    monkeypatch.setattr(public_data, "_fetch_json", fake_fetch)
    r = client.get("/api/public/benefits?page=2&per_page=10")
    assert r.status_code == 200
    assert r.json()["data"][0]["서비스명"] == "테스트 혜택"
    assert captured["url"] == f"{public_data.GOV24_BASE_URL}/serviceList"
    assert captured["params"]["serviceKey"] == "server-only-key"
    assert captured["params"]["page"] == 2
    assert captured["params"]["perPage"] == 10


def test_benefit_conditions_proxy_filters_by_service_id(client, monkeypatch):
    monkeypatch.setenv("GOV24_SERVICE_KEY", "server-only-key")
    captured = {}

    async def fake_fetch(url, params, source):
        captured.update(url=url, params=params, source=source)
        return {"data": []}

    monkeypatch.setattr(public_data, "_fetch_json", fake_fetch)
    r = client.get("/api/public/benefits/svc-123/conditions")
    assert r.status_code == 200
    assert captured["url"] == f"{public_data.GOV24_BASE_URL}/supportConditions"
    assert captured["params"]["cond[서비스ID::EQ]"] == "svc-123"


def test_lh_notices_proxy_formats_dates_and_limits_type(client, monkeypatch):
    monkeypatch.setenv("LH_SERVICE_KEY", "lh-server-only-key")
    captured = {}

    async def fake_fetch(url, params, source):
        captured.update(url=url, params=params, source=source)
        return {"dsList": []}

    monkeypatch.setattr(public_data, "_fetch_json", fake_fetch)
    r = client.get(
        "/api/public/lh-notices",
        params={"page": 2, "per_page": 10, "start_date": "2025-01-02", "end_date": "2025-02-03"},
    )
    assert r.status_code == 200
    assert captured["url"] == public_data.LH_URL
    assert captured["params"]["ServiceKey"] == "lh-server-only-key"
    assert captured["params"]["UPP_AIS_TP_CD"] == "06"
    assert captured["params"]["PAN_NT_ST_DT"] == "2025.01.02"
    assert captured["params"]["CLSG_DT"] == "2025.02.03"
    assert captured["params"]["PAGE"] == 2


def test_lh_notices_rejects_reversed_date_range(client, monkeypatch):
    monkeypatch.setenv("LH_SERVICE_KEY", "lh-server-only-key")
    r = client.get(
        "/api/public/lh-notices",
        params={"start_date": "2025-02-03", "end_date": "2025-01-02"},
    )
    assert r.status_code == 422
