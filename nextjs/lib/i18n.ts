// @ts-nocheck

export const LANGUAGE_STORAGE_KEY = 'hsam-review-language';

export function normalizeLanguage(value) {
  return value === 'en' ? 'en' : 'ko';
}

export function isEnglish(language) {
  return normalizeLanguage(language) === 'en';
}

const UI_TEXT = {
  ko: {
    'languageToggle.label': '언어',
    'languageToggle.on': '영어 ON',
    'languageToggle.off': '영어 OFF',
    'languageToggle.aria': '영어 모드 켜기/끄기',

    'login.title': '리뷰어 로그인',
    'login.reviewerId': '리뷰어 ID',
    'login.password': '비밀번호',
    'login.reviewerPlaceholder': '아이디를 입력하세요.',
    'login.passwordPlaceholder': '비밀번호를 입력하세요.',
    'login.submit': '로그인',
    'login.submitting': '로그인 중...',
    'login.redirecting': '이동 중...',
    'login.checking': '아이디와 비밀번호를 확인하고 있습니다.',
    'login.redirectMessage': '로그인 확인 완료. 페이지로 이동하고 있습니다.',
    'login.failed': '로그인에 실패했습니다.',
    'login.requestFailed': '로그인 요청 중 오류가 발생했습니다.',
    'login.error.missingReviewerId': 'Reviewer ID를 입력하세요.',
    'login.error.missingPassword': '비밀번호를 입력하세요.',
    'login.error.invalidCredentials': '등록되지 않았거나 비밀번호가 올바르지 않습니다.',

    'error.dataLoadTitle': '데이터를 불러오지 못했습니다.',
    'error.adminLoadTitle': '관리자 분석을 불러오지 못했습니다.',

    'app.reviewerId': 'Reviewer ID',
    'app.logout': '로그아웃',
    'app.saveToCloud': '클라우드에 저장',
    'app.noAssignedTitle': '할당된 이미지가 없습니다.',
    'app.noAssignedBody': 'Reviewer {reviewerId} 에게 연결된 review_assignments 행이 없습니다.',
    'app.missingItems': '남은 항목',
    'app.fullTree': '전체 트리',
    'app.saveFailed': '저장에 실패했습니다.',
    'saveStatus.idle': '대기 중',
    'saveStatus.saving': '저장 중...',
    'saveStatus.saved': '클라우드에 저장됨',
    'saveStatus.dirty': '저장되지 않은 변경사항',
    'saveStatus.error': '저장 오류',

    'imageList.title': '이미지',
    'imageList.recommendedOrder': '추천 순서',
    'imageList.defaultOrder': '기본 순서',
    'imageList.overallProgress': '전체 진행도 {completed}/{total} ({percent}%)',
    'imageList.progress': '진행도: {done}/{total}',
    'imageList.complete': '{percent}% 완료',

    'hierarchy.title': '전체 트리',
    'hierarchy.progress': '진행도',
    'hierarchy.treeQuestion': '전체 트리 질문',
    'hierarchy.complete': '완료',
    'hierarchy.incomplete': '미완료',
    'hierarchy.disabledHint': '모든 노드를 완료해야 전체 트리 질문이 활성화됩니다.',

    'questions.nodeTitle': '노드 질문',
    'questions.treeTitle': '전체 트리 질문',

    'visual.overlay': '오버레이',
    'visual.maskedOriginal': '마스크 적용 원본',
    'visual.mask': '마스크',
    'visual.originalImage': '원본 이미지',
    'visual.remainingArea': '남은 영역',
    'visual.fullOverlay': '전체 오버레이',
    'visual.treeReview': '전체 트리 평가',
    'visual.noTreeImages': '전체 트리 검토용 이미지를 찾지 못했습니다.',
    'visual.noNodeImages': '노드 검토용 이미지를 찾지 못했습니다.',
    'visual.instances': '인스턴스',
    'visual.instanceItem': '인스턴스 {index}',
    'visual.showInstances': '인스턴스 보기 ({count})',
    'visual.hideInstances': '인스턴스 숨기기 ({count})',
    'visual.items': '{count}개',
    'visual.loading': '불러오는 중...',
    'visual.nodePathAria': '노드 경로',

    'modal.zoomAria': '{title} 확대 보기',
    'modal.closeAria': '확대 보기 닫기',
    'modal.prevAria': '이전 이미지',
    'modal.nextAria': '다음 이미지',
    'modal.current': '현재',

    'inspector.current': '현재',
    'inspector.parent': '부모',
    'inspector.children': '자식',
    'inspector.depth': '깊이',
    'inspector.path': '경로',
  },
  en: {
    'languageToggle.label': 'Language',
    'languageToggle.on': 'English ON',
    'languageToggle.off': 'English OFF',
    'languageToggle.aria': 'Toggle English mode',

    'login.title': 'Reviewer Login',
    'login.reviewerId': 'Reviewer ID',
    'login.password': 'Password',
    'login.reviewerPlaceholder': 'Enter your ID.',
    'login.passwordPlaceholder': 'Enter your password.',
    'login.submit': 'Log in',
    'login.submitting': 'Logging in...',
    'login.redirecting': 'Redirecting...',
    'login.checking': 'Checking your ID and password.',
    'login.redirectMessage': 'Login confirmed. Redirecting to the review page.',
    'login.failed': 'Login failed.',
    'login.requestFailed': 'An error occurred while signing in.',
    'login.error.missingReviewerId': 'Enter your Reviewer ID.',
    'login.error.missingPassword': 'Enter your password.',
    'login.error.invalidCredentials': 'This account is not registered or the password is incorrect.',

    'error.dataLoadTitle': 'Data failed to load.',
    'error.adminLoadTitle': 'Admin analytics failed to load.',

    'app.reviewerId': 'Reviewer ID',
    'app.logout': 'Logout',
    'app.saveToCloud': 'Save to cloud',
    'app.noAssignedTitle': 'No assigned images.',
    'app.noAssignedBody': 'No review_assignments row is connected to Reviewer {reviewerId}.',
    'app.missingItems': 'Remaining Items',
    'app.fullTree': 'Full Tree',
    'app.saveFailed': 'Failed to save.',
    'saveStatus.idle': 'Idle',
    'saveStatus.saving': 'Saving...',
    'saveStatus.saved': 'Saved to cloud',
    'saveStatus.dirty': 'Unsaved changes',
    'saveStatus.error': 'Save error',

    'imageList.title': 'Images',
    'imageList.recommendedOrder': 'Recommended',
    'imageList.defaultOrder': 'Default order',
    'imageList.overallProgress': 'Overall progress {completed}/{total} ({percent}%)',
    'imageList.progress': 'Progress: {done}/{total}',
    'imageList.complete': '{percent}% complete',

    'hierarchy.title': 'Full Tree',
    'hierarchy.progress': 'Progress',
    'hierarchy.treeQuestion': 'Full-tree question',
    'hierarchy.complete': 'Complete',
    'hierarchy.incomplete': 'Incomplete',
    'hierarchy.disabledHint': 'Complete every node to enable the full-tree question.',

    'questions.nodeTitle': 'Node Questions',
    'questions.treeTitle': 'Full-Tree Questions',

    'visual.overlay': 'Overlay',
    'visual.maskedOriginal': 'Masked Original',
    'visual.mask': 'Mask',
    'visual.originalImage': 'Original Image',
    'visual.remainingArea': 'Remaining Area',
    'visual.fullOverlay': 'Full Overlay',
    'visual.treeReview': 'Full-Tree Review',
    'visual.noTreeImages': 'No images were found for full-tree review.',
    'visual.noNodeImages': 'No images were found for node review.',
    'visual.instances': 'Instances',
    'visual.instanceItem': 'Instance {index}',
    'visual.showInstances': 'Show instances ({count})',
    'visual.hideInstances': 'Hide instances ({count})',
    'visual.items': '{count} items',
    'visual.loading': 'Loading...',
    'visual.nodePathAria': 'Node path',

    'modal.zoomAria': 'Open enlarged view for {title}',
    'modal.closeAria': 'Close enlarged view',
    'modal.prevAria': 'Previous image',
    'modal.nextAria': 'Next image',
    'modal.current': 'Current',

    'inspector.current': 'Current',
    'inspector.parent': 'Parent',
    'inspector.children': 'Children',
    'inspector.depth': 'Depth',
    'inspector.path': 'Path',
  },
};

const ANSWER_LABELS_EN = {
  '예': 'Yes',
  '아니오': 'No',
  '판단불가': 'Cannot Determine',
  '모두 포함함': 'Covers All',
  '약간 놓침': 'Slightly Missing',
  '많이 놓침': 'Largely Missing',
  '포함하지 않음': 'No Extra',
  '약간 포함': 'Slight Extra',
  '많이 포함': 'Large Extra',
  '정확': 'Accurate',
  '수용 가능': 'Acceptable',
  '부정확': 'Inaccurate',
  '실패': 'Failed',
  '없음': 'None',
  '조금 있음': 'Some',
  '많이 있음': 'Many',
  '맞음': 'Correct',
  '대체로 맞음': 'Mostly Correct',
  '부분적으로 맞음': 'Partly Correct',
  '아님': 'Incorrect',
  '좋음': 'Good',
  '매우 좋음': 'Very Good',
  '보통': 'Neutral',
  '나쁨': 'Bad',
};

export function uiText(language, key, values = {}) {
  const lang = normalizeLanguage(language);
  const template = UI_TEXT[lang]?.[key] || UI_TEXT.ko[key] || key;
  return String(template).replace(/\{(\w+)\}/g, (_, name) => {
    const value = values?.[name];
    return value === undefined || value === null ? '' : String(value);
  });
}

export function answerOptionLabel(value, language) {
  const raw = String(value || '');
  return isEnglish(language) ? ANSWER_LABELS_EN[raw] || raw : raw;
}

export function dateLocaleFor(language) {
  return isEnglish(language) ? 'en-US' : 'ko-KR';
}
