# HWBench 평가 확장

사용자가 합의한 두 트랙을 한 번의 goal로 구현하고 검증한다.

1. 상용 EDA 없이 수행 가능한 과제·난이도·실패·반복 지표와 CVDP no-commercial/Heavy 연결. 기존 native 과제와 공식 upstream 경로를 구분한다.
2. 기능 PASS 후 RTLA/PowerPro 중심의 RTL 추정·합성 기준 PPA 및 lint/Xprop 품질 평가. 최종 제출물만 실행하며 장시간 도구 작업은 큐·예산·캐시·반입을 지원한다.

현재 사외이므로 proprietary EDA binary/license/library 실행은 하지 못한다. 실제 도구의 미확인 CLI나 보고서 형식을 지어내지 않고 wrapper 계약, 원본 보고서 보존, mock/fixture 회귀 및 사내 연결 절차를 완성한다. 실제 상용 PPA·실제 모델 성능·공식 CVDP 전체 점수를 검증했다고 주장하지 않는다.

완료 기준: 사용 가능한 CLI end-to-end 경로, real RTL/git positive/negative controls, pinned public catalog의 수량·분류 검사, EDA queue/cache/import/timeout/invalid-evidence 회귀, 독립 리뷰, 한국어 단일 HTML 가이드 및 새 검증 증거. 도구가 없는 특정 실행은 기록하되 나머지 구현을 멈추지 않는다.

보드 truth는 state.yaml이다. 기본 실행은 stdlib와 사전 설치된 도구만 필요하며 네트워크 자동 다운로드를 하지 않는다. 외부 자료는 개발 중 pinned revision으로 별도 반입 준비한다. 에이전트와 hidden checker 격리는 명시적으로 유지한다.

사용자 재확인: 사내 실행 환경은 외부 접속이 불가능하다. 데이터셋·sanitized Git bundle·evaluator·컨테이너 이미지·런타임을 외부 준비 단계에서 반입하며 SHA256과 revision을 검사한다. 사내 실행 경로는 fetch/pull/install/외부 API fallback을 하지 않는다. 명시한 사내 모델 endpoint와 license server만 사용한다. 네트워크 차단 검증으로 이를 확인한다.
