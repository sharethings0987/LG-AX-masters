"""policies.json을 DB에 다시 반영한다.

    python -m app.seed

키가 같은 정책은 덮어쓰고, JSON에 없는 정책(관리 API로 추가한 것)은 그대로 둔다.
"""
from . import db
from .schemas import PolicyIn


def main() -> None:
    data = db.load_seed()
    for p in data["policies"]:  # 잘못된 규칙이 DB에 들어가기 전에 막는다
        PolicyIn.model_validate({k: v for k, v in p.items() if k != "key"})
    db.init_db()
    conn = db.connect()
    try:
        n = db.seed(conn)
        conn.commit()
    finally:
        conn.close()
    print(f"정책 {n}개를 {db.DB_PATH}에 반영했습니다.")


if __name__ == "__main__":
    main()
