(() => {
  const PAGE_SIZE = 20;
  const API_BASE = (window.AL_API_BASE_URL || (location.protocol === 'file:' ? 'http://127.0.0.1:8000' : '')).replace(/\/+$/, '');
  const statusEl = document.getElementById('status');
  const itemsEl = document.getElementById('items');
  const previous = document.getElementById('prev');
  const next = document.getElementById('next');
  const pageLabel = document.getElementById('page-label');
  let tab = 'benefits';
  let page = 1;
  let totalPages = null;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
  const safeUrl = value => {
    try {
      const url = new URL(String(value), location.href);
      return url.protocol === 'https:' ? url.href : '';
    } catch {
      return '';
    }
  };
  const first = (item, ...keys) => {
    for (const key of keys) if (item && item[key] != null && item[key] !== '') return item[key];
    return '';
  };
  const rowsFrom = payload => {
    const candidates = [
      payload?.data, payload?.dsList, payload?.items?.item, payload?.items,
      payload?.response?.body?.items?.item, payload?.response?.body?.items,
    ];
    const rows = candidates.find(value => Array.isArray(value) || (value && typeof value === 'object'));
    return Array.isArray(rows) ? rows : rows ? [rows] : [];
  };
  const getTotalPages = payload => {
    const total = Number(first(payload, 'totalCount', 'total_count', 'ALL_CNT', 'dsTotalCnt'));
    const perPage = Number(first(payload, 'perPage', 'per_page', 'PG_SZ')) || PAGE_SIZE;
    return Number.isFinite(total) && total > 0 ? Math.ceil(total / perPage) : null;
  };

  async function request(path) {
    const response = await fetch(`${API_BASE}${path}`, { headers: { Accept: 'application/json' } });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data?.detail || `HTTP ${response.status}`;
      throw new Error(String(detail));
    }
    return data;
  }

  function sourceLink(item, isLh) {
    const url = safeUrl(first(item, isLh ? 'DTL_URL' : '상세조회URL', '온라인신청사이트URL'));
    return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">공식 안내 보기</a>` : '';
  }

  function benefitCard(item, index) {
    const id = first(item, '서비스ID', 'serviceId');
    const title = first(item, '서비스명', 'serviceName');
    const detail = first(item, '지원내용', '서비스목적요약', '서비스목적');
    const conditions = first(item, '지원대상', '선정기준');
    const provider = first(item, '소관기관명', '접수기관', '접수기관명');
    const deadline = first(item, '신청기한');
    const actions = `${sourceLink(item, false)}${id ? `<button type="button" data-conditions="${esc(id)}" data-index="${index}">지원 조건 보기</button>` : ''}`;
    return `<article class="card"><h2>${esc(title || '공공서비스')}</h2><div class="meta">${esc(provider)}${deadline ? ` · 신청기한 ${esc(deadline)}` : ''}</div>${detail ? `<p class="content">${esc(detail)}</p>` : ''}${conditions ? `<p class="content"><b>지원대상·선정기준</b><br>${esc(conditions)}</p>` : ''}<div class="actions">${actions}</div><div id="conditions-${index}"></div></article>`;
  }

  function lhCard(item) {
    const title = first(item, 'PAN_NM');
    const area = first(item, 'CNP_CD_NM');
    const type = first(item, 'AIS_TP_CD_NM', 'UPP_AIS_TP_NM');
    const state = first(item, 'PAN_SS');
    const posted = first(item, 'PAN_NT_ST_DT');
    const closing = first(item, 'CLSG_DT');
    return `<article class="card"><h2>${esc(title || 'LH 임대공고')}</h2><div class="meta">${esc(area)}${type ? ` · ${esc(type)}` : ''}${state ? ` · ${esc(state)}` : ''}</div><p class="content">${posted ? `공고일 ${esc(posted)}` : ''}${closing ? ` · 마감 ${esc(closing)}` : ''}</p><div class="actions">${sourceLink(item, true)}</div></article>`;
  }

  function updatePager(count) {
    pageLabel.textContent = `${page} 페이지`;
    previous.disabled = page <= 1;
    next.disabled = totalPages != null ? page >= totalPages : count < PAGE_SIZE;
  }

  async function load() {
    statusEl.className = 'status';
    statusEl.textContent = '불러오는 중…';
    itemsEl.replaceChildren();
    previous.disabled = true;
    next.disabled = true;
    pageLabel.textContent = '';
    const path = tab === 'benefits'
      ? `/api/public/benefits?page=${page}&per_page=${PAGE_SIZE}`
      : `/api/public/lh-notices?page=${page}&per_page=${PAGE_SIZE}`;
    try {
      const payload = await request(path);
      const rows = rowsFrom(payload);
      totalPages = getTotalPages(payload);
      itemsEl.innerHTML = rows.length
        ? rows.map((item, index) => tab === 'benefits' ? benefitCard(item, index) : lhCard(item)).join('')
        : '<div class="card">표시할 공고가 없습니다.</div>';
      statusEl.textContent = '';
      updatePager(rows.length);
    } catch (error) {
      statusEl.className = 'status error';
      statusEl.textContent = `정보를 불러오지 못했습니다: ${error.message.replace(/[.。]+$/, '')}. 백엔드 주소와 API 인증키 설정을 확인해 주세요.`;
      pageLabel.textContent = '';
    }
  }

  async function showConditions(button) {
    const target = document.getElementById(`conditions-${button.dataset.index}`);
    button.disabled = true;
    button.textContent = '불러오는 중…';
    try {
      const payload = await request(`/api/public/benefits/${encodeURIComponent(button.dataset.conditions)}/conditions`);
      const rows = rowsFrom(payload);
      target.innerHTML = `<div class="conditions-list">${rows.length
        ? rows.map(row => `<div>${Object.entries(row).map(([key, value]) => `<b>${esc(key)}</b>: ${esc(value)}`).join(' · ')}</div>`).join('')
        : '등록된 지원 조건 정보가 없습니다.'}</div>`;
      button.remove();
    } catch (error) {
      target.innerHTML = `<div class="conditions-list error">${esc(error.message)}</div>`;
      button.disabled = false;
      button.textContent = '다시 시도';
    }
  }

  document.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    tab = button.dataset.tab;
    page = 1;
    document.querySelectorAll('[data-tab]').forEach(item => item.classList.toggle('active', item === button));
    load();
  }));
  previous.addEventListener('click', () => { if (page > 1) { page -= 1; load(); } });
  next.addEventListener('click', () => { page += 1; load(); });
  itemsEl.addEventListener('click', event => {
    const button = event.target.closest('[data-conditions]');
    if (button) showConditions(button);
  });
  load();
})();
