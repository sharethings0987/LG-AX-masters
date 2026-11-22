(() => {
  const $ = (id) => document.getElementById(id);
  const formatCount = (value) => new Intl.NumberFormat("ko-KR").format(value);
  const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]);

  let summary;

  function renderPopulation(data) {
    const series = data.monthly;
    const first = series[0];
    const latest = series[series.length - 1];
    const delta = latest.total - first.total;
    $("population-current").textContent = `${formatCount(latest.total)}명`;
    $("population-change").textContent =
      `1월 대비 ${delta > 0 ? "+" : ""}${formatCount(delta)}명`;

    const values = series.map((item) => item.total);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const points = values.map((value, index) => {
      const x = 30 + index * (480 / Math.max(1, values.length - 1));
      const y = 22 + (1 - (value - min) / range) * 92;
      return { x, y, value };
    });
    const pointList = points.map((point) => `${point.x},${point.y}`).join(" ");
    const circles = points.map((point, index) =>
      `<circle cx="${point.x}" cy="${point.y}" r="3.5"><title>${escapeHtml(series[index].period.slice(4))}월 ${formatCount(point.value)}명</title></circle>`
    ).join("");
    const labels = series.map((item, index) => {
      if (index % 2 !== 0 && index !== series.length - 1) return "";
      const x = points[index].x;
      return `<text x="${x}" y="145" text-anchor="middle">${escapeHtml(item.period.slice(4))}월</text>`;
    }).join("");
    $("population-chart").innerHTML =
      `<svg class="chart" viewBox="0 0 540 160" role="img" aria-label="2025년 월별 전국 주민등록인구 추이">` +
      `<line x1="30" y1="22" x2="510" y2="22" stroke="#eee8f3"/>` +
      `<line x1="30" y1="114" x2="510" y2="114" stroke="#eee8f3"/>` +
      `<polyline points="${pointList}" fill="none" stroke="#a8467a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<g fill="#a8467a">${circles}</g>${labels}</svg>` +
      `<div class="meta">1월 ${formatCount(first.total)}명 → 12월 ${formatCount(latest.total)}명</div>`;
  }

  function renderBars(container, items, denominator) {
    const rows = items.map((item) => {
      const share = item.count / denominator * 100;
      return `<li><div class="bar-label"><span>${escapeHtml(item.label)}</span>` +
        `<span>${formatCount(item.count)} · ${share.toFixed(1)}%</span></div>` +
        `<div class="track"><i style="width:${Math.min(100, share)}%"></i></div></li>`;
    }).join("");
    $(container).innerHTML = `<ul class="bars">${rows}</ul>`;
  }

  function groupPopulationByDecade(rows) {
    const groups = new Map();
    for (const row of rows) {
      const age = Number.parseInt(row.age, 10);
      if (!Number.isFinite(age)) continue;
      const start = Math.floor(age / 10) * 10;
      const label = start >= 100 ? "100세 이상" : `${start}~${start + 9}세`;
      const group = groups.get(label) || { label, total: 0, male: 0, female: 0 };
      group.total += row.total;
      group.male += row.male;
      group.female += row.female;
      groups.set(label, group);
    }
    return [...groups.values()];
  }

  function renderScaledBars(container, items) {
    const max = Math.max(1, ...items.map((item) => item.value));
    $(container).innerHTML = `<ul class="bars">${items.map((item) =>
      `<li><div class="bar-label"><span>${escapeHtml(item.label)}</span>` +
      `<span>${formatCount(item.value)}명</span></div>` +
      `<div class="track"><i style="width:${item.value / max * 100}%"></i></div></li>`
    ).join("")}</ul>`;
  }

  function renderPopulationAgeBars(sex = "total") {
    const grouped = groupPopulationByDecade(summary.population.ageDistribution);
    renderScaledBars(
      "population-age-bars",
      grouped.map((item) => ({ label: item.label, value: item[sex] })),
    );
  }

  function renderAgeBars(sex = "total") {
    const rows = summary.singleHouseholds.byAge;
    renderScaledBars(
      "age-bars",
      rows.map((row) => ({ label: row.age, value: row[sex] })),
    );
  }

  function renderRegions(query = "") {
    const all = summary.households.regionsByOnePersonShare;
    const matching = query
      ? all.filter((item) => item.name.includes(query))
      : all.slice(0, 10);
    $("region-count").textContent = query
      ? `${matching.length}개 지역`
      : "비율 상위 10개";
    $("region-rows").innerHTML = matching.length
      ? matching.map((item) =>
        `<tr><th scope="row">${escapeHtml(item.name)}</th>` +
        `<td>${formatCount(item.onePerson)} / ${formatCount(item.total)}</td>` +
        `<td>${item.onePersonSharePercent.toFixed(1)}%</td></tr>`
      ).join("")
      : '<tr><td colspan="3">검색 결과가 없습니다.</td></tr>';
  }

  function renderSources(sources) {
    $("sources").innerHTML = sources.map((source) =>
      `<li><a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">` +
      `${escapeHtml(source.title)} · KOSIS</a></li>`
    ).join("");
  }

  function render(data) {
    summary = data;
    const households = data.households;
    $("household-total").textContent = `${formatCount(households.total)}가구`;
    $("average-household").textContent = `평균 가구원 ${households.averageSize.toFixed(1)}명`;
    $("single-share").textContent = `${households.onePersonSharePercent.toFixed(1)}%`;
    $("single-total").textContent = `${formatCount(households.onePerson)}가구`;

    renderPopulation(data.population);
    renderPopulationAgeBars();
    renderBars("household-bars", households.bySize, households.total);
    renderBars(
      "housing-bars",
      data.singleHouseholds.byType,
      data.singleHouseholds.total,
    );
    renderAgeBars();
    renderRegions();
    renderSources(data.sources);
    $("status").hidden = true;
    $("dashboard").hidden = false;
  }

  async function load() {
    try {
      const response = await fetch("public-data/kosis-2025.json", { cache: "no-cache" });
      if (!response.ok) {
        throw new Error(`통계 파일 요청 실패 (HTTP ${response.status})`);
      }
      render(await response.json());
    } catch (error) {
      $("status").classList.add("error");
      $("status").textContent = `통계를 불러오지 못했습니다: ${error.message}`;
    }
  }

  $("age-sex").addEventListener("change", (event) => renderAgeBars(event.target.value));
  $("population-sex").addEventListener("change", (event) =>
    renderPopulationAgeBars(event.target.value),
  );
  $("region-filter").addEventListener("input", (event) =>
    renderRegions(event.target.value.trim()),
  );
  load();
})();
