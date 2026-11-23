"""인생그램 백엔드: 정책 데이터 API + 편지·플레이 기록 저장."""
from __future__ import annotations

import json
import os
import random
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Path as PathParam, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .public_data import router as public_data_router
from .youth_quiz import router as youth_quiz_router
from .schemas import (
    LetterIn, LetterOut, PlayCreated, PlayIn, PlayPatch, PlaySummary,
    PolicyCatalog, PolicyIn, PolicyOut,
)

KeyParam = PathParam(..., pattern=r"^[a-z][a-z0-9_]{1,31}$")

FRONTEND_DIR = Path(os.environ.get("AL_FRONTEND_DIR", db.APP_DIR.parent.parent / "frontend"))
VARIANTS = ["A", "B", "C"]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="인생그램 API", version="0.1.0", lifespan=lifespan)
app.include_router(public_data_router)
app.include_router(youth_quiz_router)

# HTML을 file://로 직접 열어도 API를 부를 수 있게 개발 중엔 모든 출처를 허용한다.
# 배포 시 AL_CORS_ORIGINS="https://example.com,https://www.example.com" 처럼 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.environ.get("AL_CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    token = os.environ.get("AL_ADMIN_TOKEN")
    if not token:
        raise HTTPException(403, "관리 API가 꺼져 있습니다. 서버를 AL_ADMIN_TOKEN 환경변수와 함께 실행하세요.")
    if not secrets.compare_digest(x_admin_token or "", token):
        raise HTTPException(401, "X-Admin-Token이 올바르지 않습니다.")


def _policy(row: sqlite3.Row) -> PolicyOut:
    return PolicyOut(
        key=row["key"], name=row["name"], site=row["site"], hint=row["hint"],
        description=row["description"], requirements=json.loads(row["requirements"]),
        effects=json.loads(row["effects"]), active=bool(row["active"]),
        sort_order=row["sort_order"], updated_at=row["updated_at"],
    )


# ---------------------------------------------------------------- 상태

@app.get("/api/health", tags=["system"])
def health(conn: sqlite3.Connection = Depends(db.get_db)):
    n = conn.execute("SELECT COUNT(*) FROM policies WHERE active = 1").fetchone()[0]
    return {"ok": True, "active_policies": n}


# ---------------------------------------------------------------- 정책

@app.get("/api/policies", response_model=PolicyCatalog, tags=["policies"])
def list_policies(conn: sqlite3.Connection = Depends(db.get_db)):
    """게임이 시작할 때 불러가는 정책 목록 (활성 정책만) + 공식 사이트 도메인."""
    sites = {r["name"]: r["domain"] for r in conn.execute("SELECT name, domain FROM sites")}
    rows = conn.execute("SELECT * FROM policies WHERE active = 1 ORDER BY sort_order, key").fetchall()
    return PolicyCatalog(sites=sites, policies=[_policy(r) for r in rows])


@app.get("/api/policies/{key}", response_model=PolicyOut, tags=["policies"])
def get_policy(key: str = KeyParam, conn: sqlite3.Connection = Depends(db.get_db)):
    row = conn.execute("SELECT * FROM policies WHERE key = ?", (key,)).fetchone()
    if not row:
        raise HTTPException(404, "없는 정책입니다.")
    return _policy(row)


@app.put("/api/policies/{key}", response_model=PolicyOut, tags=["policies"], dependencies=[Depends(require_admin)])
def upsert_policy(body: PolicyIn, key: str = KeyParam, conn: sqlite3.Connection = Depends(db.get_db)):
    """정책 추가·수정 (관리자). 비활성화하려면 active=false로 보낸다."""
    if not conn.execute("SELECT 1 FROM sites WHERE name = ?", (body.site,)).fetchone():
        raise HTTPException(422, f"등록되지 않은 사이트입니다: {body.site}")
    order = body.sort_order
    if order is None:
        cur = conn.execute("SELECT sort_order FROM policies WHERE key = ?", (key,)).fetchone()
        order = cur[0] if cur else conn.execute("SELECT COALESCE(MAX(sort_order) + 1, 0) FROM policies").fetchone()[0]
    conn.execute(
        f"""INSERT INTO policies(key, name, site, hint, description, requirements, effects, active, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
              name = excluded.name, site = excluded.site, hint = excluded.hint,
              description = excluded.description, requirements = excluded.requirements,
              effects = excluded.effects, active = excluded.active,
              sort_order = excluded.sort_order, updated_at = {db.NOW}""",
        (
            key, body.name, body.site, body.hint, body.description,
            json.dumps([r.model_dump(exclude_none=True) for r in body.requirements], ensure_ascii=False),
            json.dumps(body.effects, ensure_ascii=False), int(body.active), order,
        ),
    )
    return _policy(conn.execute("SELECT * FROM policies WHERE key = ?", (key,)).fetchone())


# ---------------------------------------------------------------- 편지

@app.post("/api/letters", response_model=LetterOut, status_code=201, tags=["letters"])
def create_letter(body: LetterIn, conn: sqlite3.Connection = Depends(db.get_db)):
    play_id = body.play_id
    if play_id is not None:
        owner = conn.execute("SELECT player_id FROM plays WHERE id = ?", (play_id,)).fetchone()
        if not owner or owner[0] != body.player_id:
            play_id = None  # 남의 기록이나 없는 기록에는 연결하지 않는다
    cur = conn.execute(
        "INSERT INTO letters(player_id, play_id, recipient, text) VALUES (?, ?, ?, ?)",
        (body.player_id, play_id, body.to, body.text),
    )
    row = conn.execute("SELECT * FROM letters WHERE id = ?", (cur.lastrowid,)).fetchone()
    return LetterOut(id=row["id"], to=row["recipient"], text=row["text"], play_id=row["play_id"], created_at=row["created_at"])


@app.get("/api/letters", response_model=list[LetterOut], tags=["letters"])
def list_letters(
    player_id: str = Query(..., pattern=r"^[A-Za-z0-9_-]{8,64}$"),
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    rows = conn.execute(
        "SELECT * FROM letters WHERE player_id = ? ORDER BY id DESC LIMIT ?", (player_id, limit)
    ).fetchall()
    return [LetterOut(id=r["id"], to=r["recipient"], text=r["text"], play_id=r["play_id"], created_at=r["created_at"]) for r in rows]


# ---------------------------------------------------------------- 플레이 기록

@app.post("/api/plays", response_model=PlayCreated, status_code=201, tags=["plays"])
def create_play(body: PlayIn, conn: sqlite3.Connection = Depends(db.get_db)):
    """마흔 살 엔딩에 도달했을 때 한 번 저장."""
    j = lambda v: json.dumps(v, ensure_ascii=False)
    cur = conn.execute(
        """INSERT INTO plays(player_id, variant, mode, care, auto, character, result,
                             eligible, done, missed, heard, year_map)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            body.player_id, body.variant, body.mode, body.care, int(body.auto),
            j(body.character.model_dump()), j(body.result.model_dump()),
            j(body.eligible), j(body.done), j(body.missed), j(body.heard),
            j([y.model_dump() for y in body.year_map]),
        ),
    )
    row = conn.execute("SELECT id, created_at FROM plays WHERE id = ?", (cur.lastrowid,)).fetchone()
    return PlayCreated(id=row["id"], created_at=row["created_at"])


@app.patch("/api/plays/{play_id}", response_model=PlayCreated, tags=["plays"])
def update_play(play_id: int, body: PlayPatch, conn: sqlite3.Connection = Depends(db.get_db)):
    """엔딩 화면에서 고른 「마음속 목표」「고마웠던 것」 답을 기록."""
    row = conn.execute("SELECT player_id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not row or row[0] != body.player_id:
        raise HTTPException(404, "기록을 찾을 수 없습니다.")
    sets, args = [], []
    for col in ("goal_answer", "thanks_answer"):
        if col in body.model_fields_set:
            sets.append(f"{col} = ?")
            args.append(getattr(body, col))
    if sets:
        conn.execute(f"UPDATE plays SET {', '.join(sets)}, updated_at = {db.NOW} WHERE id = ?", (*args, play_id))
    out = conn.execute("SELECT id, created_at FROM plays WHERE id = ?", (play_id,)).fetchone()
    return PlayCreated(id=out["id"], created_at=out["created_at"])


@app.get("/api/plays", response_model=list[PlaySummary], tags=["plays"])
def list_plays(
    player_id: str = Query(..., pattern=r"^[A-Za-z0-9_-]{8,64}$"),
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(db.get_db),
):
    rows = conn.execute(
        "SELECT * FROM plays WHERE player_id = ? ORDER BY id DESC LIMIT ?", (player_id, limit)
    ).fetchall()
    return [
        PlaySummary(
            id=r["id"], variant=r["variant"], mode=r["mode"],
            character=json.loads(r["character"]), result=json.loads(r["result"]),
            done=json.loads(r["done"]), eligible=json.loads(r["eligible"]),
            goal_answer=r["goal_answer"], thanks_answer=r["thanks_answer"], created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------- 통계

@app.get("/api/stats", tags=["stats"])
def stats(conn: sqlite3.Connection = Depends(db.get_db)):
    """버전별 플레이 수와, 정책별로 '대상이었던 플레이 중 실제로 챙긴 비율'."""
    by_variant = [
        dict(r) for r in conn.execute(
            """SELECT variant, COUNT(*) AS plays,
                      ROUND(AVG(json_array_length(done)), 2) AS avg_done,
                      ROUND(AVG(json_array_length(eligible)), 2) AS avg_eligible,
                      ROUND(AVG(json_extract(result, '$.stats.mood')), 1) AS avg_final_mood
               FROM plays GROUP BY variant ORDER BY variant"""
        )
    ]

    def counts(col: str) -> dict[str, int]:
        q = f"SELECT j.value AS k, COUNT(*) AS n FROM plays, json_each(plays.{col}) AS j GROUP BY j.value"
        return {r["k"]: r["n"] for r in conn.execute(q)}

    elig, done, heard = counts("eligible"), counts("done"), counts("heard")
    names = {r["key"]: r["name"] for r in conn.execute("SELECT key, name FROM policies ORDER BY sort_order")}
    policies = [
        {
            "key": k, "name": n,
            "eligible": elig.get(k, 0), "heard": heard.get(k, 0), "done": done.get(k, 0),
            "take_up_rate": round(done.get(k, 0) / elig[k], 3) if elig.get(k) else None,
        }
        for k, n in names.items()
    ]
    total = conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]
    return {"total_plays": total, "by_variant": by_variant, "policies": policies}


# ---------------------------------------------------------------- 프론트엔드

@app.get("/", include_in_schema=False)
def root():
    """A/B/C 중 하나로 무작위 배정."""
    return RedirectResponse(f"/another_life_v8{random.choice(VARIANTS)}.html", status_code=307)


if FRONTEND_DIR.is_dir():
    # API 라우트보다 뒤에 마운트해야 /api/* 가 가려지지 않는다.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR), name="frontend")
