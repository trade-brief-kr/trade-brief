'use strict';
/*
 * 국가 정보 탭
 * data/country-stats.json 을 먼저 불러오고, 실패하면(file:// 직접 열기 등)
 * data/country-stats.js 가 제공하는 window.COUNTRY_STATS 를 사용한다.
 * 값이 없으면 추정하지 않고 '—'와 '데이터 없음(출처 링크)'으로 표시한다.
 */
(() => {
  const STORAGE_KEY = 'tradeBrief.statsCountry';
  const panel = document.getElementById('country-info');
  if (!panel) return;

  let data = null;
  let selectedDept = '';
  let selectedCountry = '';

  // ------------------------------------------------------------ 유틸

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));

  const safeUrl = (url) => {
    try {
      const parsed = new URL(url);
      return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : '';
    } catch {
      return '';
    }
  };

  const link = (url, label) => {
    const href = safeUrl(url);
    return href
      ? `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`
      : esc(label);
  };

  const number = (value, digits = 0) => value.toLocaleString('ko-KR', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  /** 달러 금액을 한국식 단위(조·억·만 달러)로 표기 */
  function usd(value) {
    const abs = Math.abs(value);
    const sign = value < 0 ? '-' : '';
    if (abs >= 1e12) return `${sign}${number(abs / 1e12, 2)}조 달러`;
    if (abs >= 1e8) return `${sign}${number(abs / 1e8, abs >= 1e10 ? 0 : 1)}억 달러`;
    if (abs >= 1e4) return `${sign}${number(abs / 1e4, 0)}만 달러`;
    return `${sign}${number(abs, 0)}달러`;
  }

  const isNumber = (value) => typeof value === 'number' && Number.isFinite(value);

  function missing(url, label) {
    return `<p class="stat-value is-missing">—</p>
      <p class="stat-meta">데이터 없음 (${link(url, label)})</p>`;
  }

  function findDeptName(id) {
    return data?.departments?.find((d) => d.id === id)?.name || '';
  }

  function formatKst(iso) {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return '';
    const parts = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(date).reduce((acc, p) => ({ ...acc, [p.type]: p.value }), {});
    return `${parts.year}.${parts.month}.${parts.day} ${parts.hour}:${parts.minute} KST`;
  }

  // ------------------------------------------------------------ 지표 카드

  function worldBankCard(title, item, format) {
    let body;
    if (item && isNumber(item.value)) {
      body = `<p class="stat-value">${esc(format(item.value))}</p>
        <p class="stat-meta">${esc(item.year)}년 기준 · ${link(item.url, `World Bank (${item.license || 'CC BY 4.0'})`)}</p>`;
    } else {
      body = missing(item?.url || 'https://data.worldbank.org/', 'World Bank');
    }
    return `<article class="stat-card"><h3>${esc(title)}</h3>${body}</article>`;
  }

  function rateCard(country) {
    const item = country.policyRate || {};
    let body;
    if (isNumber(item.value)) {
      body = `<p class="stat-value">${esc(number(item.value, 2))}%</p>
        <p class="stat-meta">${esc(item.date)} 기준 · ${link(item.url, 'BIS 정책금리')}</p>`;
    } else {
      const bank = country.centralBank || {};
      body = `<p class="stat-value is-missing">—</p>
        <p class="stat-meta">데이터 없음 (BIS 미수록 · ${link(bank.url, bank.name || '중앙은행')})</p>`;
    }
    return `<article class="stat-card"><h3>정책금리</h3>${body}</article>`;
  }

  function tradeRows(record) {
    const balanceClass = record.balance >= 0 ? 'is-surplus' : 'is-deficit';
    return `<dl class="trade-grid">
        <div><dt>수출</dt><dd>${esc(usd(record.exports))}</dd></div>
        <div><dt>수입</dt><dd>${esc(usd(record.imports))}</dd></div>
        <div><dt>수지</dt><dd class="${balanceClass}">${esc(usd(record.balance))}</dd></div>
      </dl>`;
  }

  function tradeBlock(label, record, sourceHtml) {
    if (!record) return '';
    return `<section class="trade-block">
        <h4>${esc(label)} <span>${esc(record.period)}</span></h4>
        ${tradeRows(record)}
        <p class="stat-meta">${sourceHtml}</p>
      </section>`;
  }

  function tradeCard(country) {
    const trade = country.trade || {};
    const customs = trade.customs;
    const comtrade = trade.comtrade;
    const blocks = [];

    if (customs) {
      const fetched = customs.fetchedAt ? ` · 수집 ${esc(String(customs.fetchedAt).slice(0, 10))}` : '';
      const src = `${link(customs.url, '관세청 수출입무역통계')}${fetched}`;
      blocks.push(tradeBlock('최근 월', customs.monthly, src));
      blocks.push(tradeBlock('최근 12개월', customs.last12, src));
      blocks.push(tradeBlock('연간', customs.annual, src));
    }
    if (comtrade) {
      const src = `${link(comtrade.url, 'UN Comtrade')} · 한국 보고 기준${comtrade.note ? ` · ${esc(comtrade.note)}` : ''}`;
      if (!customs?.annual) blocks.push(tradeBlock('연간', comtrade.annual, src));
      if (!customs?.monthly) blocks.push(tradeBlock('최근 공개 월', comtrade.monthly, src));
    }

    const content = blocks.filter(Boolean).join('');
    const customsStatus = data?.status?.customs?.status;
    const note = !customs && customsStatus && customsStatus !== 'ok'
      ? `<p class="stat-note">관세청 월별 실적은 아직 연동되지 않아 UN Comtrade 공개값을 표시합니다. (${link(data.sources?.customs?.url, '관세청 국가별 수출입실적')})</p>`
      : '';

    return `<article class="stat-card stat-card--wide">
        <h3>한국과의 교역 <small>한국 기준 · 수출 FOB / 수입 CIF</small></h3>
        ${content || missing(data?.sources?.comtrade?.url || 'https://comtradeplus.un.org/', 'UN Comtrade')}
        ${note}
      </article>`;
  }

  // ------------------------------------------------------------ 화면 구성

  function countriesOf(deptId) {
    return (data.countries || []).filter((c) => !deptId || c.dept === deptId);
  }

  function renderPicker() {
    const deptOptions = (data.departments || [])
      .map((d) => `<option value="${esc(d.id)}"${d.id === selectedDept ? ' selected' : ''}>${esc(d.name)}</option>`)
      .join('');

    const groups = (data.departments || [])
      .filter((d) => !selectedDept || d.id === selectedDept)
      .map((d) => {
        const chips = countriesOf(d.id).map((c) => `
          <button type="button" class="country-chip" data-country="${esc(c.id)}"
            aria-pressed="${c.id === selectedCountry}">${esc(c.name)}</button>`).join('');
        return `<div class="chip-group"><p class="chip-group-title">${esc(d.name)}</p><div class="chips">${chips}</div></div>`;
      }).join('');

    return `<article class="card stats-picker">
        <div class="stats-head">
          <div>
            <p class="eyebrow">COUNTRY PROFILE</p>
            <h2>국가 정보</h2>
          </div>
          <p class="stats-updated">데이터 갱신 ${esc(formatKst(data.generatedAt))}</p>
        </div>
        <label class="stats-dept">소관과
          <select id="stats-dept"><option value="">전체</option>${deptOptions}</select>
        </label>
        <div class="chip-groups">${groups}</div>
      </article>`;
  }

  function renderDetail(country) {
    if (!country) return '';
    const dept = findDeptName(country.dept);
    const group = country.group ? ` · ${esc(country.group)}` : '';
    return `<article class="card stats-detail" aria-live="polite">
        <div class="stats-detail-head">
          <h2>${esc(country.name)}</h2>
          <p class="muted">${esc(dept)}${group}</p>
        </div>
        <div class="stat-cards">
          ${worldBankCard('GDP (명목, 달러)', country.gdp, usd)}
          ${worldBankCard('1인당 GDP', country.gdpPerCapita, (v) => `${number(v, 0)}달러`)}
          ${worldBankCard('인플레이션 (CPI, 연간)', country.inflation, (v) => `${number(v, 1)}%`)}
          ${rateCard(country)}
          ${tradeCard(country)}
        </div>
      </article>`;
  }

  function cell(value) {
    return value ? esc(value) : '<span class="is-missing">—</span>';
  }

  function tradeSummary(country) {
    const t = country.trade || {};
    const record = t.customs?.annual || t.comtrade?.annual;
    return record ? `${usd(record.exports + record.imports)} (${record.period})` : '';
  }

  function renderTable() {
    const rows = countriesOf(selectedDept).map((c) => `
      <tr data-country="${esc(c.id)}"${c.id === selectedCountry ? ' class="is-selected"' : ''}>
        <th scope="row"><button type="button" class="link-button" data-country="${esc(c.id)}">${esc(c.name)}</button></th>
        <td>${cell(isNumber(c.gdp?.value) ? usd(c.gdp.value) : '')}</td>
        <td>${cell(isNumber(c.gdpPerCapita?.value) ? `${number(c.gdpPerCapita.value, 0)}달러` : '')}</td>
        <td>${cell(isNumber(c.inflation?.value) ? `${number(c.inflation.value, 1)}%` : '')}</td>
        <td>${cell(isNumber(c.policyRate?.value) ? `${number(c.policyRate.value, 2)}%` : '')}</td>
        <td>${cell(tradeSummary(c))}</td>
      </tr>`).join('');

    return `<article class="card stats-table-card">
        <h2>한눈에 보기 <small>${esc(findDeptName(selectedDept) || '전체 국가')}</small></h2>
        <div class="table-scroll">
          <table class="stats-table">
            <thead><tr>
              <th scope="col">국가</th><th scope="col">GDP</th><th scope="col">1인당 GDP</th>
              <th scope="col">인플레이션</th><th scope="col">정책금리</th><th scope="col">한국과 교역액(연간)</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <p class="stat-meta">기준연도·기준일은 국가별 카드에서 확인. '—'는 출처에 값이 없는 항목.</p>
      </article>`;
  }

  function renderSources() {
    const s = data.sources || {};
    const customs = data.status?.customs || {};
    const customsText = customs.status === 'ok'
      ? (customs.source === 'file'
        ? `반영됨(국내 PC 수집${customs.latestPeriod ? `, 최근 월 ${customs.latestPeriod}` : ''})`
        : '연동됨')
      : '미연동(수집기 준비됨, 국내 네트워크에서 실행 필요)';
    return `<article class="card stats-sources">
        <h2>출처</h2>
        <ul>
          <li>GDP·1인당 GDP·인플레이션: ${link(s.worldBank?.url, 'World Bank Open Data')} (${esc(s.worldBank?.license || 'CC BY 4.0')})</li>
          <li>정책금리: ${link(s.bis?.url, 'BIS Central bank policy rates')}. 미수록 국가는 각국 중앙은행 링크 제공</li>
          <li>한국과의 교역: ${link(s.customs?.url, '관세청 국가별 수출입실적')} ${esc(customsText)} · 대체 ${link(s.comtrade?.url, 'UN Comtrade')} (한국 보고 기준)</li>
        </ul>
      </article>`;
  }

  function render() {
    if (!data) return;
    const visible = countriesOf(selectedDept);
    if (!visible.some((c) => c.id === selectedCountry)) {
      selectedCountry = visible[0]?.id || '';
    }
    const country = (data.countries || []).find((c) => c.id === selectedCountry);
    panel.innerHTML = renderPicker() + renderDetail(country) + renderTable() + renderSources();
  }

  function select(countryId, scroll) {
    selectedCountry = countryId;
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ dept: selectedDept, country: countryId })); } catch { /* 저장 불가 무시 */ }
    render();
    if (scroll) panel.querySelector('.stats-detail')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  panel.addEventListener('click', (event) => {
    const target = event.target.closest('[data-country]');
    if (target && target.tagName === 'BUTTON') select(target.dataset.country, target.classList.contains('link-button'));
  });

  panel.addEventListener('change', (event) => {
    if (event.target.id === 'stats-dept') {
      selectedDept = event.target.value;
      selectedCountry = '';
      select(countriesOf(selectedDept)[0]?.id || '', false);
    }
  });

  /** 브리프 상단에서 고른 소관과·국가가 있으면 국가 정보 탭에도 반영 */
  function syncFromBriefControls() {
    if (!data) return;
    const dept = document.getElementById('department')?.value || '';
    const countryName = document.getElementById('country')?.value || '';
    if (!dept) return;
    const match = (data.countries || []).find((c) => c.name === countryName && c.dept === dept);
    selectedDept = dept;
    selectedCountry = match ? match.id : '';
    render();
  }

  document.getElementById('country-tab')?.addEventListener('click', syncFromBriefControls);

  // ------------------------------------------------------------ 로딩

  function restore() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
      selectedDept = saved.dept || '';
      selectedCountry = saved.country || '';
    } catch { /* 무시 */ }
  }

  function valid(value) {
    return value && Array.isArray(value.countries) && Array.isArray(value.departments);
  }

  async function load() {
    restore();
    try {
      const response = await fetch(`data/country-stats.json?v=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(String(response.status));
      const json = await response.json();
      if (!valid(json)) throw new Error('format');
      data = json;
    } catch {
      data = valid(window.COUNTRY_STATS) ? window.COUNTRY_STATS : null;
    }
    if (!data) {
      panel.innerHTML = `<article class="card"><h2>국가 정보를 불러오지 못했습니다</h2>
        <p>data/country-stats.json 이 없습니다. <code>python3 tools/fetch_country_stats.py</code> 를 실행해 생성하세요.</p></article>`;
      return;
    }
    applyQuery();
    render();
  }

  /**
   * 링크 공유용: index.html?tab=country 또는 ?tab=country&country=SA 로 국가 정보 탭을 바로 연다.
   * (#해시는 브리프의 날짜 보관함이 사용하므로 쿼리 문자열을 쓴다)
   */
  function applyQuery() {
    const params = new URLSearchParams(location.search);
    if (params.get('tab') !== 'country') return;
    const code = (params.get('country') || '').toUpperCase();
    const country = code && data.countries.find((c) => c.id === code);
    if (country) {
      selectedDept = country.dept;
      selectedCountry = country.id;
    }
    const tabButton = document.getElementById('country-tab');
    tabButton?.removeEventListener('click', syncFromBriefControls);
    tabButton?.click();
    tabButton?.addEventListener('click', syncFromBriefControls);
  }

  load();
})();
