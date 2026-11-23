/* 인생그램 · 실제 청년정책 「진짜 공식 안내 찾기」 (v8 A·B·C 공용)
 * 캐릭터 상황(나이·지역·취업상태·결혼)에 맞는 실제 정책을 백엔드 /api/public/youth-quiz 에서 미리 받아 두었다가
 * 갈림길에 「이런 정책이 있대」로 알려 주고, 검색 결과 4개 중 진짜 공식 안내를 골라야 혜택을 받는다.
 * 게임 스크립트와 backend.js 다음에 로드되며 G, S, MOD, JB, TG, makeDec, pickDecision, tickMonth,
 * modalBody, addLine, chg, esc, fxT, draw, loop 를 그대로 쓴다. 서버에 연결되지 않으면 아무 일도 하지 않는다.
 */
(() => {
  if (typeof pickDecision !== 'function' || typeof makeDec !== 'function') return;

  const API = (window.AL_API_BASE_URL || (location.protocol.startsWith('http') ? '' : 'http://127.0.0.1:8000'))
    .replace(/\/+$/, '');
  // 주소에 ?yq=1 을 붙이면 금방, 자주 나온다 (직접 확인용).
  const TEST = /[?&]yq=1\b/.test(location.search);
  const FIRST_MONTH = TEST ? 1 : 4;
  const GAP = TEST ? [2, 3] : [12, 18];   // 다음 정책까지 간격(개월)
  const MAX_PER_GAME = TEST ? 30 : 10;
  const TRIES = 2;
  const FETCH_TIMEOUT = 45000;            // Render 무료 서버는 깨어나는 데 시간이 걸린다

  const SIDO = {
    '11': '서울특별시', '12': '전남광주통합특별시', '26': '부산광역시', '27': '대구광역시', '28': '인천광역시',
    '30': '대전광역시', '31': '울산광역시', '36': '세종특별자치시', '41': '경기도', '43': '충청북도',
    '44': '충청남도', '47': '경상북도', '48': '경상남도', '50': '제주특별자치도', '51': '강원특별자치도',
    '52': '전북특별자치도',
  };
  const REGION_SIDO = {
    '서울': ['11'],
    '경기·인천': ['41', '41', '28'],
    '비수도권 대도시': ['26', '27', '30', '31', '12'],
    '지방 소도시': ['43', '44', '47', '48', '52', '51', '50', '12'],
  };
  const INTRO = {
    job: '취업 준비에 보탬이 될 제도가 없을까 찾아보다가',
    house: '집 문제로 머리가 복잡하던 참에',
    money: '돈 걱정을 덜 방법을 찾아보다가',
    salary: '월급을 어떻게 모을지 고민하다가',
  };
  const REWARD = {
    job: { self: 4, prep: 1, hp: 2 },
    house: { money: 3, burn: -3, hp: 2 },
    money: { money: 4, self: 2, hp: 1 },
  };
  const EMP_LABEL = { unemployed: '미취업', employed: '재직 중', freelancer: '프리랜서', founder: '창업', student: '대학생' };
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const sentence = t => { t = String(t || '').trim(); return !t || /[.!?다요…]$/.test(t) ? t : t + '.'; };

  const state = g => {
    if (!g.yq) g.yq = { next: FIRST_MONTH, count: 0, seen: [], ready: null, loading: false, hint: null, cur: null };
    if (!g.yq.sido) g.yq.sido = pick(REGION_SIDO[g.me.rg] || ['11']);
    g.yq.sidoName = SIDO[g.yq.sido];
    return g.yq;
  };

  const employment = g => g.job === '대학생' ? 'student' : g.job === '프리랜서' ? 'freelancer'
    : g.job === '창업' ? 'founder' : (JB[g.job] && JB[g.job].e) ? 'employed' : 'unemployed';

  function situation(g, q) {
    if (q.hint && g.m - q.hint.m <= 6) return q.hint.tag;
    const J = JB[g.job] || {};
    const c = [];
    if (J.s == 1 || g.job === '쉬는중' || (g.job === '대학생' && g.m >= 30)) c.push('job');
    if (g.h === '월세' || g.h === '전세' || (g.h === '본가' && g.age >= 25)) c.push('house');
    if (J.e || g.debt >= 300 || g.st.money < 25 || g.job === '대학생') c.push('money');
    return c.length ? pick(c) : null;
  }

  // 받아 둔 정책이 지금 캐릭터에도 그대로 맞는지 (나이·직업·결혼이 바뀌면 버린다)
  const profile = g => [g.age, employment(g), g.f.married ? 1 : 0, g.f.kid ? 1 : 0, g.h].join('|');
  const HOUSE = { 본가: 'parents', 월세: 'monthly', 전세: 'jeonse', 자가: 'owner' };
  // 백엔드가 걸러 주지 못한 경우(예전 서버·GitHub Pages)에도 엔진의 ctxOk로 한 번 더 거른다: 자녀·신혼·주택 구입·재직 등 키워드
  const policyFits = (g, P) => typeof ctxOk !== 'function' ||
    ctxOk({ n: P.name, t: P.name, d: P.summary, support: P.support, target: P.target, x: P.age && P.age !== '나이 제한 없음' ? P.age : '' }, g);
  const meText = g => `만 ${g.age}세 · ${SIDO[state(g).sido]} · ${EMP_LABEL[employment(g)]}${g.f.married ? ' · 기혼' : ''}`;

  function prefetch(g) {
    const q = state(g);
    const sit = situation(g, q);
    if (!sit) { q.next = g.m + 3; return; }
    q.loading = true;
    const params = new URLSearchParams({
      situation: sit, age: String(g.age), sido: q.sido, employment: employment(g),
      married: g.f.married ? 'true' : 'false', kid: g.f.kid ? 'true' : 'false', house: HOUSE[g.h] || 'parents',
      exclude: q.seen.slice(-40).join(','),
    });
    const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = ctl && setTimeout(() => ctl.abort(), FETCH_TIMEOUT);
    fetch(`${API}/api/public/youth-quiz?${params}`, ctl ? { signal: ctl.signal } : {})
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(data => {
        if (G !== g || !data || !data.policy || !Array.isArray(data.results) || data.results.length < 2) return;
        if (!policyFits(g, data.policy)) {
          console.info('[ctxOk] 지금 상황과 맞지 않는 청년정책을 걸러냄:', data.policy.name);
          q.seen.push(data.policy.id); q.next = g.m + 1; return;
        }
        q.ready = { data, sit, profile: profile(g), m: g.m };
      })
      .catch(e => {
        console.info('[인생그램] 청년정책을 받지 못했습니다.', e.message);
        if (G === g) q.next = g.m + (TEST ? 1 : 2);
      })
      .finally(() => { if (timer) clearTimeout(timer); q.loading = false; });
  }

  /* ---------- 갈림길: 「이런 정책이 있대」 ---------- */
  function announce(g, ready) {
    const q = state(g), P = ready.data.policy;
    q.ready = null;
    q.count++;
    q.next = g.m + GAP[0] + Math.floor(Math.random() * (GAP[1] - GAP[0] + 1));
    q.seen.push(P.id);
    makeDec({
      id: 'yq',
      w: '🔎 청년정책',
      t: `「${P.name}」`,
      x: `${(ready.sit === 'money' && ['employed', 'freelancer', 'founder'].includes(employment(g)) ? INTRO.salary : INTRO[ready.sit]) || INTRO.money} 「${P.name}」이라는 정책을 알게 됐다. ${sentence(P.summary)} `
        + `지금 내 조건(${meText(g)})이면 받을 수 있을 것 같다. 받으려면 진짜 공식 안내를 찾아 신청해야 한다.`,
      ch: [
        { t: '바로 검색해서 신청해본다', act: () => openSearch(g, ready) },
        { t: '다음에 알아보자', act: () => addLine(`「${P.name}」은 나중에 알아보기로 했다. 그러다 잊어버렸다.`, 'n', null, 'c', 2) },
      ],
    });
  }

  /* ---------- 검색 화면: 진짜 공식 안내 고르기 ---------- */
  function openSearch(g, ready) {
    state(g).cur = { ready, tries: TRIES, dead: {}, why: '', view: 'search' };
    MOD = { k: 'yq' };
  }

  function choose(i) {
    const g = G, s = g && g.yq && g.yq.cur;
    if (!s || s.view !== 'search') return;
    const r = s.ready.data.results[i];
    if (!r || s.dead[i]) return;
    const P = s.ready.data.policy;
    if (r.ok) {
      const fx = REWARD[s.ready.sit] || REWARD.money;
      chg(fx);
      s.view = 'got';
      s.fx = fx;
      addLine(`✅ 진짜 공식 안내(${r.url.replace('/…', '')})를 찾아 「${P.name}」을 신청했다. (${fxT(fx) || '준비도 +1'})`, 'g', null, 'c', 5);
    } else {
      s.dead[i] = 1;
      s.tries--;
      s.why = r.why;
      if (s.tries <= 0) {
        s.view = 'fail';
        chg({ burn: 2 });
        addLine(`「${P.name}」을 찾다가 엉뚱한 사이트만 헤맸다. 시간만 날렸다.`, 'b', null, 'u', 3);
      }
    }
    draw();
  }

  function close() {
    const g = G, s = g && g.yq && g.yq.cur;
    if (s && s.view === 'search') addLine(`「${s.ready.data.policy.name}」 검색 창을 닫았다. 다음에 다시 알아봐야지.`, 'n', null, 'c', 2);
    if (g && g.yq) g.yq.cur = null;
    MOD = null;
    draw();
    if (typeof loop === 'function') loop();
  }

  const ymd = t => String(t || '').replace(/(\d{4})(\d{2})(\d{2})/g, '$1.$2.$3');
  const safeUrl = u => /^https:\/\//.test(String(u || '')) ? String(u) : '';

  function searchBody(s) {
    const d = s.ready.data;
    const rows = d.results.map((r, i) => {
      const dead = !!s.dead[i];
      return `<button type="button" class="yq-r${dead ? ' dead' : ''}" data-yq="r:${i}" ${dead ? 'disabled' : ''}>
        <span class="yq-u">${esc(r.url)}</span>
        <span class="yq-t">${dead ? '❌ ' : ''}${esc(r.title)}</span>
        <span class="yq-s">${esc(r.snippet)}</span></button>`;
    }).join('');
    return `<div class="yq-sheet"><div class="yq-bar">🔍 <b>${esc(d.policy.name)}</b></div>
      <div class="yq-mu">남은 시도 ${s.tries}회 · 진짜 공식 안내를 골라보세요</div>
      ${s.why ? `<div class="yq-why">❌ ${esc(s.why)}</div>` : ''}
      ${rows}
      <button type="button" class="yq-close" data-yq="close">닫기</button></div>`;
  }

  function resultBody(s) {
    const d = s.ready.data, P = d.policy, got = s.view === 'got';
    const official = d.results.find(r => r.ok);
    const url = safeUrl(P.url);
    const fakes = d.results.filter(r => !r.ok)
      .map(r => `<div class="yq-mu">❌ <b>${esc(r.url)}</b> — ${esc(r.why)}</div>`).join('');
    return `<div class="yq-sheet">
      <div class="yq-mu">🔎 실제 청년정책 · ${esc(d.situation_label || '')}</div>
      <h3 class="se" style="margin:4px 0 8px">${got ? '✅ 진짜 공식 안내를 찾았어요!' : '❌ 시도를 모두 써 버렸어요'}</h3>
      <div class="yq-card"><b>${esc(P.name)}</b><div class="yq-mu">${esc(P.org)}</div>
        ${P.summary ? `<p style="margin:6px 0">${esc(P.summary)}</p>` : ''}
        ${P.support ? `<div class="yq-mu">지원 내용: ${esc(P.support)}</div>` : ''}
        ${P.apply_period ? `<div class="yq-mu">신청 기간: ${esc(ymd(P.apply_period))}</div>` : ''}</div>
      <div style="margin:10px 0 4px"><b>나는 대상일까?</b></div>
      ${d.checks.map(c => `<div class="lg">✔ ${esc(c)}</div>`).join('')}
      ${P.extra ? `<div class="yq-mu" style="margin-top:6px">⚠️ 추가로 확인할 조건: ${esc(P.extra)}</div>` : ''}
      ${got ? `<p>효과: ${esc(fxT(s.fx) || '준비도 +1')}</p>`
            : `<p>진짜 공식 안내는 <b>${esc(official ? official.url : '')}</b> 였어요. 공공기관 주소는 .go.kr·.or.kr로 끝나요.</p>`}
      <div style="margin:6px 0 10px"><b>나머지는 왜 가짜였을까?</b>${fakes}</div>
      ${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">공식 안내 보기 ↗</a>` : ''}
      <p class="yq-mu" style="font-size:12px">온통청년(youthcenter.go.kr)에 등록된 실제 정책이에요. 신청 전에는 공식 안내에서 최신 조건과 기간을 꼭 확인하세요.</p>
      <button class="btn" data-yq="close">계속하기</button></div>`;
  }

  function body() {
    const s = G && G.yq && G.yq.cur;
    if (!s) return '<button class="btn" data-yq="close">닫기</button>';
    return s.view === 'search' ? searchBody(s) : resultBody(s);
  }

  document.addEventListener('click', e => {
    const b = e.target.closest('[data-yq]');
    if (!b || !G) return;
    const a = b.dataset.yq;
    if (a === 'close') close();
    else if (a.startsWith('r:')) choose(+a.slice(2));
  });

  const css = document.createElement('style');
  css.textContent = `
    .yq-sheet{--yq-link:#2747c9}
    @media (prefers-color-scheme:dark){.yq-sheet{--yq-link:#9fb3ff}}
    .yq-bar{background:var(--ln);border-radius:999px;padding:10px 16px;margin-bottom:8px}
    .yq-mu{color:var(--mu);font-size:13px;margin:2px 0}
    .yq-why{color:var(--b);font-size:13px;margin:6px 0}
    .yq-r{display:block;width:100%;text-align:left;font:inherit;color:inherit;background:var(--card);border:1px solid var(--ln);border-radius:10px;padding:10px 14px;margin:8px 0;cursor:pointer}
    .yq-r:hover{border-color:var(--ac)}
    .yq-r span{display:block}
    .yq-u{color:var(--g);font-size:12px}
    .yq-t{color:var(--yq-link);font-weight:700;margin:2px 0}
    .yq-s{color:var(--mu);font-size:13px}
    .yq-r.dead{opacity:.45;cursor:default;text-decoration:line-through}
    .yq-close{display:block;margin:10px auto 0;background:none;border:0;color:var(--mu);text-decoration:underline;font:inherit;cursor:pointer}
    .yq-card{border:1px solid var(--ln);border-radius:10px;padding:10px 14px}`;
  document.head.appendChild(css);

  /* ---------- 게임 함수에 끼워 넣기 ---------- */
  const origMakeDec = makeDec;
  makeDec = function (ev) {
    // 직전 이벤트의 꼬리표(취업·주거·돈)를 기억해 다음 정책 주제로 쓴다.
    const tag = ev && typeof TG !== 'undefined' && TG[ev.id];
    if (G && (tag === 'job' || tag === 'house' || tag === 'money')) state(G).hint = { tag, m: G.m };
    return origMakeDec.apply(this, arguments);
  };

  const origPick = pickDecision;
  pickDecision = function () {
    const g = G;
    if (g && !g.auto && g.yq && g.yq.ready && (typeof polOk !== 'function' || polOk())) {
      const ready = g.yq.ready;
      if (ready.profile === profile(g) && g.m - ready.m <= 6 && policyFits(g, ready.data.policy)) return announce(g, ready);
      g.yq.ready = null; // 상황이 바뀌어 맞지 않는 정책은 버린다
    }
    return origPick.apply(this, arguments);
  };

  const origTick = tickMonth;
  tickMonth = function () {
    const r = origTick.apply(this, arguments);
    const g = G;
    if (g && S === 'play' && !g.auto) {
      const q = state(g);
      if (!q.loading && !q.ready && q.count < MAX_PER_GAME && g.m >= q.next) prefetch(g);
    }
    return r;
  };

  const origBody = modalBody;
  modalBody = function () {
    if (MOD && MOD.k === 'yq') return body();
    return origBody.apply(this, arguments);
  };
})();
