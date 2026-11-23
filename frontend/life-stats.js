/* Another Station · 인생 통계 상수
 * 게임 안의 모든 확률과 기간은 여기서만 읽는다(another_life_v9S.html 엔진이 window.LIFE를 쓴다).
 * [통계] = 공식 통계·보도에서 가져온 값, [기획] = 게임 밸런스를 위해 정한 값.
 */
window.LIFE = (() => {
  // ── 통계 값 ──────────────────────────────────────────────

  // [통계] 2025학년도 일반고 졸업생 대학 진학률 — 학교알리미 공시 분석(한국경제 생글생글, 2026.1)
  //   any = 4년제+전문대 합산, univ4 = 4년제만
  //   '경기·인천'의 any는 공시 분석에 합산값이 없어 [기획] 추정치 0.70을 쓴다.
  //   '비수도권 대도시'와 '지방 소도시'는 둘 다 지방권 평균을 쓴다.
  const COLLEGE_RATE = {
    전국: {any: .790, univ4: .635},
    서울: {any: .642, univ4: .462},
    '경기·인천': {any: .70 /* [기획] 추정 */, univ4: .555},
    '비수도권 대도시': {any: .857, univ4: .745},
    '지방 소도시': {any: .857, univ4: .745},
  };

  // [통계] 고교생 졸업 후 진로 희망 — 2025 초·중등 진로교육 현황조사
  const CAREER_HOPE = {college: .649, job: .156, startup: .033};

  // [통계] 대졸자 평균 졸업 소요기간 — 2026.5 경제활동인구조사 청년층 부가조사 (단위: 개월)
  //   전체 4년 5.7개월, 남 5년 2.1개월, 여 3년 11.6개월
  const GRAD_MONTHS = {all: 53.7, M: 62.1, F: 47.6};

  // [통계] 휴학 경험자 평균 휴학기간 1년 9.9개월 — 같은 조사 (단위: 개월)
  const LEAVE_AVG_MONTHS = 21.9;

  // [통계] 청년(15~29세) 고용률·실업률, 졸업 후 미취업자 중 1년 이상 비율 — 같은 조사
  const YOUTH = {employRate: .438, unemployRate: .072, longJobless: .486};

  // [통계] 군 복무기간(육군) 18개월 — 병무청
  const ARMY_MONTHS = 18;

  // [통계] 이름: 2006년생(2026년에 20세) 전후 출생신고 인기 이름 — 대법원 전자가족관계등록시스템 「이름 통계」(출생 연도별 상위 이름)
  //   성별에 맞는 이름만 뽑는다(본인·친구·연인 공통). 지원·하늘·유진·현서처럼 남녀 모두 흔한 이름은 뺐다.
  const NAMES = {
    m: ['민준', '현우', '지훈', '동현', '준혁', '도현', '승민', '민재', '준영', '현준', '지호', '건우', '우진', '성민', '예준',
        '민성', '준서', '승현', '시우', '정우', '승우', '태민', '민혁', '재현', '상현'],
    f: ['서연', '민서', '지민', '서현', '수빈', '예은', '하은', '지우', '서윤', '채원', '윤서', '다은', '수연', '지은', '예린',
        '민지', '은지', '소연', '예진', '가은', '지현', '혜원', '유나', '나연'],
  };

  // ── 기획 값 (밸런스용) ────────────────────────────────────

  // [기획] 재수 선택 확률: 진학 희망자 중 약 12%. 형편이 여유로울수록 높게(형편 보정을 그대로 더한다).
  const RETAKE_RATE = .12;
  // [기획] 재수할 때마다 합격 확률에 더하는 값
  const RETAKE_BONUS = .08;
  // [기획] 형편(q 1~5) 보정: 진학 확률에 더하고 0~0.97로 자른다.
  const Q_ADJ = {1: -.15, 2: -.08, 3: 0, 4: .06, 5: .10};
  const CLAMP_MAX = .97;
  // [기획] 휴학 확률: 여학생 약 30%, 남학생은 군 휴학과 별개로 일반 휴학 약 25%
  const LEAVE_P = {F: .30, M: .25};
  // [기획] 한 번 휴학할 때 길이(개월)와 비중. 휴학 경험자 평균(약 22개월)에 가깝도록 두 번째 휴학 확률을 둔다.
  const LEAVE_LEN = [[6, .35], [12, .45], [18, .2]];
  const LEAVE_AGAIN_P = .35;
  // [기획] 전문대 중 3년제 학과 비율
  const COLLEGE3_P = .20;
  // [기획] 졸업 유예를 고를 확률(자동결정 기준)과 유예 기간
  const DEFER_P = .15, DEFER_MONTHS = 6;
  // [기획] 바로 취업을 고른 고졸자 중 바로 일자리를 구하는 비율(나머지는 구직 중)
  const HS_JOB_P = .70;
  // [기획] 남성 중 「먼저 군대에 간다」를 고르는 비율(자동결정 기준)
  const ARMY_FIRST_P = .06;
  // [기획] 입대를 미룰 수 있는 마지막 나이(이 나이 중에는 반드시 입대)
  const ARMY_LAST_AGE = 23;
  // [기획] 대학생 남성의 입대 시점 비중: 1학년 마친 뒤 / 2학년 마친 뒤
  const ARMY_STUDENT_SPLIT = {after1: .6, after2: .4};

  const clamp = p => Math.max(0, Math.min(CLAMP_MAX, p));
  const rate = rg => COLLEGE_RATE[rg] || COLLEGE_RATE.전국;

  /* 합격 확률 = 「지원했을 때 붙을 확률」.
   * [기획] 4년제는 전국 평균 지원자 합격률을 0.75로 두고 지역 4년제 진학률 차이와 형편 보정을 더한다.
   *        전문대는 0.90 기준. 재수할 때마다 RETAKE_BONUS를 더한다. */
  const ADMIT_BASE = {univ4: .75, college: .90};
  function admitP(type, rg, q, retakes) {
    const r = rate(rg), adj = Q_ADJ[q] || 0, bonus = (retakes || 0) * RETAKE_BONUS;
    const regional = type === 'univ4' ? r.univ4 - COLLEGE_RATE.전국.univ4 : (r.any - r.univ4) - (COLLEGE_RATE.전국.any - COLLEGE_RATE.전국.univ4);
    return clamp(ADMIT_BASE[type] + regional + adj + bonus);
  }

  /* 자동결정에서 진로 선택 가중치: [4년제, 전문대, 재수, 취업, 군입대]
   * 지원 비율 = 목표 진학률 ÷ 합격 확률. 그래야 「지원 → 합격」을 거친 최종 진학률이 COLLEGE_RATE(+형편 보정)에 맞는다.
   * 떨어진 사람은 후속 선택(전문대·재수·취업)으로 넘어간다. */
  // [기획] 4년제에 떨어진 뒤 자동결정 비중(형편이 여유로울수록 재수를 더 고른다)
  const FAIL_W = {college: 1.1, retake: .6, retakePerQ: .5, job: 2.4, army: .4};
  function failWeights(q, sex) {
    return {college: FAIL_W.college, retake: FAIL_W.retake + Math.max(0, q - 3) * FAIL_W.retakePerQ, job: FAIL_W.job, army: sex === 'M' ? FAIL_W.army : 0};
  }
  // [기획] 재수생이 결국 진학하는 비율(진학률 보정 계산에만 쓴다)
  const RETAKE_SUCCESS = .8;
  function careerWeights(rg, q, sex) {
    const r = rate(rg), adj = Q_ADJ[q] || 0;
    const any = clamp(r.any + adj), u4 = Math.min(any, clamp(r.univ4 + adj));
    const a4 = admitP('univ4', rg, q, 0), ac = admitP('college', rg, q, 0);
    const fw = failWeights(q, sex), fs = fw.college + fw.retake + fw.job + fw.army;
    const retake = any * clamp(RETAKE_RATE + adj);
    // 「4년제 지원 → 불합격 → 전문대·재수」로 결국 진학하는 몫까지 넣어서, 최종 진학률이 목표(any·u4)에 맞도록 지원 비율을 푼다.
    let univ = u4 / a4, college = 0;
    for (let k = 0; k < 6; k++) {
      const fail = univ * (1 - a4), reEnroll = (retake + fail * fw.retake / fs) * RETAKE_SUCCESS;
      univ = Math.max(0, Math.min(.95, (u4 - reEnroll * .7) / a4));
      college = Math.max(0, (any - u4 - reEnroll * .3 - fail * (fw.college / fs) * ac) / ac);
    }
    const army = sex === 'M' ? ARMY_FIRST_P : 0;
    const job = Math.max(.02, 1 - univ - college - retake - army);
    return [univ, college, retake, job, army];
  }

  return {
    NAMES, COLLEGE_RATE, CAREER_HOPE, GRAD_MONTHS, LEAVE_AVG_MONTHS, YOUTH, ARMY_MONTHS,
    RETAKE_RATE, RETAKE_BONUS, Q_ADJ, LEAVE_P, LEAVE_LEN, LEAVE_AGAIN_P, COLLEGE3_P,
    DEFER_P, DEFER_MONTHS, HS_JOB_P, ARMY_FIRST_P, ARMY_LAST_AGE, ARMY_STUDENT_SPLIT,
    FAIL_W, RETAKE_SUCCESS, admitP, careerWeights, failWeights, clamp,
  };
})();
