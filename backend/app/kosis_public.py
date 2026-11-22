"""Build a small, public-facing summary from the 2025 KOSIS CSV exports."""
from __future__ import annotations

import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator

ROOT_DIR = Path(__file__).resolve().parents[2]
SOURCE_DIR = ROOT_DIR / "data" / "01_KOSIS"
OUTPUT_PATH = ROOT_DIR / "frontend" / "public-data" / "kosis-2025.json"

POPULATION_FILE = "101_DT_1B04006_M_2025.csv"
HOUSEHOLD_FILE = "101_DT_1JC1516_Y_2025.csv"
SINGLE_HOUSEHOLD_FILE = "101_DT_1PL1509_Y_2025.csv"

KOSIS_ROOT = "https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId="
SOURCE_CATALOG = [
    {
        "title": "행정구역(시군구)별/1세별 주민등록인구",
        "url": KOSIS_ROOT + "DT_1B04006_M_2025",
    },
    {
        "title": "세대구성 및 가구원수별 가구(일반가구) - 시군구",
        "url": KOSIS_ROOT + "DT_1JC1516_Y_2025",
    },
    {
        "title": "성, 연령 및 거처의 종류별 1인가구 - 시군구",
        "url": KOSIS_ROOT + "DT_1PL1509_Y_2025",
    },
]


def _records(path: Path) -> Iterator[dict[str, str]]:
    with path.open(encoding="cp949", newline="") as source:
        reader = csv.reader(source)
        title = next(reader, None)
        if not title:
            raise ValueError(f"빈 KOSIS 파일입니다: {path.name}")

        headers = None
        for row in reader:
            if row and any(cell.strip() for cell in row):
                headers = [cell.strip() for cell in row]
                break
        if not headers:
            raise ValueError(f"열 이름을 찾을 수 없습니다: {path.name}")

        for line_number, row in enumerate(reader, start=4):
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(row) != len(headers):
                raise ValueError(
                    f"{path.name}:{line_number} 열 개수가 일치하지 않습니다 "
                    f"({len(row)} != {len(headers)})."
                )
            yield dict(zip(headers, (cell.strip() for cell in row)))


def _number(value: str, context: str) -> int | float | None:
    if value in {"", "X", "...", "..", "-"}:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{context} 숫자 형식이 올바르지 않습니다: {value!r}") from exc
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _required_number(record: dict[str, str], key: str) -> int | float:
    value = _number(record[key], key)
    if value is None:
        raise ValueError(f"필수 통계값이 비어 있습니다: {key}")
    return value


def _code(value: str) -> str:
    return value.strip().lstrip("'")


def build_kosis_summary(source_dir: Path = SOURCE_DIR) -> dict[str, Any]:
    population_by_month: dict[str, dict[str, int | float]] = {}
    ages_by_month: dict[str, list[dict[str, Any]]] = {}
    for record in _records(source_dir / POPULATION_FILE):
        if record["행정구역(시군구)별"] != "전국":
            continue
        period = record["시점"]
        age = record["연령별"]
        values = {
            "total": _required_number(record, "총인구수 (명)"),
            "male": _required_number(record, "남자인구수 (명)"),
            "female": _required_number(record, "여자인구수 (명)"),
        }
        if age == "계":
            if period in population_by_month:
                raise ValueError(f"주민등록인구 월별 전국 합계가 중복됩니다: {period}")
            population_by_month[period] = values
        else:
            ages_by_month.setdefault(period, []).append({"age": age, **values})

    if not population_by_month:
        raise ValueError("전국 주민등록인구 월별 합계를 찾지 못했습니다.")
    latest_period = max(population_by_month)
    latest_ages = ages_by_month.get(latest_period, [])
    for field in ("total", "male", "female"):
        if sum(item[field] for item in latest_ages) != population_by_month[latest_period][field]:
            raise ValueError(f"전국 주민등록인구 연령별 합계가 일치하지 않습니다: {field}")
    population = {
        "latestMonth": f"{latest_period[:4]}.{latest_period[4:]}",
        "monthly": [
            {"period": period, **population_by_month[period]}
            for period in sorted(population_by_month)
        ],
        "ageDistribution": latest_ages,
    }
    if not population["ageDistribution"]:
        raise ValueError(f"최근 월의 연령별 인구 자료가 없습니다: {latest_period}")

    household_total = None
    household_size_columns = [
        ("1인 (가구)", "1인"),
        ("2인 (가구)", "2인"),
        ("3인 (가구)", "3인"),
        ("4인 (가구)", "4인"),
        ("5인 (가구)", "5인"),
        ("6인 (가구)", "6인"),
        ("7인 이상 (가구)", "7인 이상"),
    ]
    province_names = {}
    regional_household_rows = []
    for record in _records(source_dir / HOUSEHOLD_FILE):
        if record["시점"] != "2025" or record["세대구성별"] != "계":
            continue
        region_name = record["행정구역별(시군구)"].strip()
        region_code = _code(record["C행정구역별(시군구)"])
        total = _required_number(record, "일반가구 (가구)")
        one_person = _required_number(record, "1인 (가구)")
        average_size = _required_number(record, "평균 가구원 수 (명)")
        if region_name == "전국":
            if household_total is not None:
                raise ValueError("일반가구 전국 합계가 중복됩니다.")
            household_total = {
                "total": total,
                "onePerson": one_person,
                "averageSize": average_size,
                "bySize": [
                    {"label": label, "count": _required_number(record, column)}
                    for column, label in household_size_columns
                ],
            }
        elif len(region_code) == 2 and region_name not in {"동부", "읍부", "면부"}:
            province_names[region_code] = region_name
        elif len(region_code) == 5 and region_name not in {"동부", "읍부", "면부"}:
            regional_household_rows.append(
                {
                    "code": region_code,
                    "name": region_name,
                    "total": total,
                    "onePerson": one_person,
                    "onePersonSharePercent": round(one_person / total * 100, 1),
                }
            )

    if household_total is None:
        raise ValueError("2025년 일반가구 전국 합계를 찾지 못했습니다.")
    if sum(item["count"] for item in household_total["bySize"]) != household_total["total"]:
        raise ValueError("가구원 수별 일반가구 합계가 일치하지 않습니다.")
    household_total["onePersonSharePercent"] = round(
        household_total["onePerson"] / household_total["total"] * 100, 1
    )
    regional_households = [
        {
            **record,
            "name": " ".join(
                part for part in (province_names.get(record["code"][:2]), record["name"]) if part
            ),
        }
        for record in regional_household_rows
    ]
    regional_households.sort(
        key=lambda item: (-item["onePersonSharePercent"], item["name"])
    )

    age_values: dict[str, dict[str, int | float]] = {}
    housing_total = None
    housing_columns = [
        ("주택_단독주택", "단독주택"),
        ("주택_아파트", "아파트"),
        ("주택_연립주택", "연립주택"),
        ("주택_다세대 주택", "다세대 주택"),
        ("주택_비주거용 건물 내 주택", "비주거용 건물 내 주택"),
        ("주택 이외의 거처_계", "주택 이외의 거처"),
    ]
    for record in _records(source_dir / SINGLE_HOUSEHOLD_FILE):
        if (
            record["행정구역별(시군구)"] != "전국"
            or record["시점"] != "2025"
        ):
            continue
        sex = record["성별"]
        age = record["연령별"]
        count = _required_number(record, "1인가구")
        if age == "합계" and sex == "계":
            if housing_total is not None:
                raise ValueError("전국 1인가구 합계가 중복됩니다.")
            housing_total = {
                "total": count,
                "byType": [
                    {"label": label, "count": _required_number(record, column)}
                    for column, label in housing_columns
                ],
            }
        elif age != "합계" and sex in {"계", "남자", "여자"}:
            values = age_values.setdefault(age, {})
            if sex in values:
                raise ValueError(f"연령별 1인가구 자료가 중복됩니다: {age}, {sex}")
            values[sex] = count

    if housing_total is None:
        raise ValueError("전국 1인가구 거처별 합계를 찾지 못했습니다.")
    if housing_total["total"] != household_total["onePerson"]:
        raise ValueError("일반가구와 1인가구 통계의 전국 합계가 일치하지 않습니다.")
    single_households_by_age = []
    for age, values in age_values.items():
        if not {"계", "남자", "여자"}.issubset(values):
            raise ValueError(f"연령별 1인가구 성별 값이 완전하지 않습니다: {age}")
        if values["남자"] + values["여자"] != values["계"]:
            raise ValueError(f"연령별 1인가구 성별 합계가 일치하지 않습니다: {age}")
        single_households_by_age.append(
            {"age": age, "total": values["계"], "male": values["남자"], "female": values["여자"]}
        )
    if sum(item["total"] for item in single_households_by_age) != housing_total["total"]:
        raise ValueError("연령별 1인가구 합계가 일치하지 않습니다.")
    if sum(item["count"] for item in housing_total["byType"]) != housing_total["total"]:
        raise ValueError("거처별 1인가구 합계가 일치하지 않습니다.")
    if any(item["onePerson"] > item["total"] for item in regional_households):
        raise ValueError("지역별 1인가구 수가 전체 가구 수를 초과합니다.")

    return {
        "year": 2025,
        "population": population,
        "households": {
            **household_total,
            "regionsByOnePersonShare": regional_households,
        },
        "singleHouseholds": {
            **housing_total,
            "byAge": single_households_by_age,
        },
        "sources": SOURCE_CATALOG,
    }


def main() -> None:
    summary = build_kosis_summary()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Generated {OUTPUT_PATH} "
        f"({len(summary['population']['monthly'])} months, "
        f"{len(summary['singleHouseholds']['byAge'])} age groups, "
        f"{len(summary['households']['regionsByOnePersonShare'])} regions)."
    )


if __name__ == "__main__":
    main()
