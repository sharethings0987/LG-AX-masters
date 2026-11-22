import csv

import pytest

from app.kosis_public import (
    HOUSEHOLD_FILE,
    POPULATION_FILE,
    SINGLE_HOUSEHOLD_FILE,
    build_kosis_summary,
)


def write_kosis_table(path, title, headers, rows):
    with path.open("w", encoding="cp949", newline="") as output:
        writer = csv.writer(output)
        writer.writerow([title])
        writer.writerow([])
        writer.writerow(headers)
        writer.writerows(rows)


@pytest.fixture()
def kosis_source(tmp_path):
    write_kosis_table(
        tmp_path / POPULATION_FILE,
        "주민등록인구",
        [
            "C행정구역(시군구)별", "행정구역(시군구)별", "C연령별", "연령별",
            "시점", "총인구수 (명)", "남자인구수 (명)", "여자인구수 (명)",
        ],
        [
            ["'00", "전국", "'000", "계", "202501", "100.0000", "49.0000", "51.0000"],
            ["'00", "전국", "'000", "계", "202502", "99.0000", "48.0000", "51.0000"],
            ["'00", "전국", "'0401", "0세", "202502", "2.0000", "1.0000", "1.0000"],
            ["'00", "전국", "'0402", "1세", "202502", "97.0000", "47.0000", "50.0000"],
        ],
    )
    write_kosis_table(
        tmp_path / HOUSEHOLD_FILE,
        "일반가구",
        [
            "C행정구역별(시군구)", "행정구역별(시군구)", "C세대구성별", "세대구성별",
            "시점", "일반가구 (가구)", "1인 (가구)", "2인 (가구)", "3인 (가구)",
            "4인 (가구)", "5인 (가구)", "6인 (가구)", "7인 이상 (가구)",
            "평균 가구원 수 (명)",
        ],
        [
            ["'00", "전국", "'00", "계", "2025", "100.0000", "20.0000", "30.0000",
             "20.0000", "15.0000", "10.0000", "3.0000", "2.0000", "2.20000"],
            ["'11", "서울특별시", "'00", "계", "2025", "100.0000", "20.0000",
             "30.0000", "20.0000", "15.0000", "10.0000", "3.0000", "2.0000", "2.20000"],
            ["'11110", "종로구", "'00", "계", "2025", "100.0000", "20.0000",
             "30.0000", "20.0000", "15.0000", "10.0000", "3.0000", "2.0000", "2.20000"],
            ["'29010", "읍부", "'00", "계", "2025", "10.0000", "2.0000",
             "3.0000", "2.0000", "1.0000", "1.0000", "1.0000", "0.0000", "2.20000"],
        ],
    )
    write_kosis_table(
        tmp_path / SINGLE_HOUSEHOLD_FILE,
        "1인가구",
        [
            "C행정구역별(시군구)", "행정구역별(시군구)", "C성별", "성별",
            "C연령별", "연령별", "시점", "1인가구", "주택_계",
            "주택_단독주택", "주택_아파트", "주택_연립주택",
            "주택_다세대 주택", "주택_비주거용 건물 내 주택",
            "주택 이외의 거처_계",
        ],
        [
            ["'00", "전국", "'0", "계", "'000", "합계", "2025", "20.0000",
             "19.0000", "6.0000", "8.0000", "1.0000", "2.0000", "1.0000", "2.0000"],
            ["'00", "전국", "'0", "계", "'024", "20세미만", "2025", "20.0000",
             "19.0000", "6.0000", "8.0000", "1.0000", "2.0000", "1.0000", "1.0000"],
            ["'00", "전국", "'1", "남자", "'024", "20세미만", "2025", "11.0000",
             "10.0000", "3.0000", "4.0000", "1.0000", "1.0000", "1.0000", "1.0000"],
            ["'00", "전국", "'2", "여자", "'024", "20세미만", "2025", "9.0000",
             "9.0000", "3.0000", "4.0000", "0.0000", "1.0000", "0.0000", "1.0000"],
        ],
    )
    return tmp_path


def test_build_kosis_summary_keeps_only_aggregates_and_validates_totals(kosis_source):
    summary = build_kosis_summary(kosis_source)

    assert summary["population"]["latestMonth"] == "2025.02"
    assert summary["population"]["monthly"][-1] == {
        "period": "202502", "total": 99, "male": 48, "female": 51,
    }
    assert summary["households"]["onePersonSharePercent"] == 20.0
    assert summary["households"]["regionsByOnePersonShare"] == [
        {
            "code": "11110",
            "name": "서울특별시 종로구",
            "total": 100,
            "onePerson": 20,
            "onePersonSharePercent": 20.0,
        }
    ]
    assert summary["singleHouseholds"]["byAge"] == [
        {"age": "20세미만", "total": 20, "male": 11, "female": 9}
    ]
    assert sum(item["count"] for item in summary["singleHouseholds"]["byType"]) == 20


def test_build_kosis_summary_rejects_duplicate_household_totals(kosis_source):
    path = kosis_source / HOUSEHOLD_FILE
    with path.open("a", encoding="cp949", newline="") as output:
        csv.writer(output).writerow(
            ["'00", "전국", "'00", "계", "2025", "100.0000", "19.0000",
             "30.0000", "20.0000", "15.0000", "10.0000", "3.0000", "2.0000", "2.20000"]
        )

    with pytest.raises(ValueError, match="중복"):
        build_kosis_summary(kosis_source)


def test_build_kosis_summary_rejects_inconsistent_national_totals(kosis_source):
    path = kosis_source / HOUSEHOLD_FILE
    with path.open(encoding="cp949", newline="") as source:
        rows = list(csv.reader(source))
    rows[3][6] = "19.0000"
    with path.open("w", encoding="cp949", newline="") as output:
        csv.writer(output).writerows(rows)

    with pytest.raises(ValueError, match="합계가 일치하지 않습니다"):
        build_kosis_summary(kosis_source)
