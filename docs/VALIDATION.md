# 구현 검증 결과

## 2026-11-07 평가 확장 검증

[보존한 검증 요약](validation/validated-expansion-20261107.json)에 실제 검증 artifact의 SHA256, 코드 해시, 단계별 판정과 문서 검증을 기록했습니다. 아래 결과는 사외 개발 환경의 구현 검증이며 실제 모델 성능이나 상용 PPA 점수가 아닙니다.

| 검증 | 확인한 결과 |
|---|---|
| 회귀 테스트 | 76개 PASS |
| Native·CVDP 변형 | 기준 RTL 통과, 선언한 오류의 기능 실패 검출 |
| 실제 Git/RTL control | 기준 통과, starter·mutant가 정상 컴파일 후 기능 실패 |
| EDA mock | native PASS 사본 → 큐 → 실행 → export/import → 캐시 → 보고·비교 |
| EDA 장애·무결성 | timeout 자식 프로세스 정리, worker 종료 watchdog, 잠금·예산 보존, 캐시 무효화, 값·단위·해시 거부 |
| 반입 실패 복구 | 두 번째 job 오류 후 올바른 묶음 재반입, 설치 중단 후 재시도, 중첩 경로 거부 |
| 격리 이식 | 원래 checkout을 마운트하지 않고 네트워크를 차단한 상태에서 native·저장소·EDA mock·전체 증거 반입 통과 |
| 실제 공개 자료 | 새 경로에 반입한 469개 pinned catalog 검사와 RVX 한 과제 준비·export 통과 |
| HTML 가이드 | 계산기 8개 경우, desktop/mobile, 인쇄, JavaScript 없는 열람, 깨진 anchor·외부 요청·script 오류·모바일 넘침 없음 |
| 한국어 교정 | humanize-korean light, 변경률 0.02%, B, 자체검증 6/6, gate 통과 |

실행한 명령과 상세 증거:

```bash
python3 scripts/validate.py
# artifacts/validation-20261106T174734Z/validation.json (UTC 이름)
python3 scripts/offline_controls.py --out artifacts/offline-t005/cvdp-final --cvdp-dir artifacts/cvdp-survey
# artifacts/offline-t005/cvdp-final/results/validation.json
node artifacts/docs-t007/browser/check.cjs
```

회귀·통합 검증은 설치된 Python/Icarus/Git/bubblewrap 등을 사용했습니다. 이식 검증은 시스템 도구를 읽기 전용으로 마운트하므로 OS 패키지 설치를 검증한 것은 아닙니다. 실제 사내 외부망 차단 정책, 모델 endpoint·인증, Docker daemon/image load, EDA 설치·라이선스·library와 vendor parser는 사내에서 확인해야 합니다.

CVDP의 nonagentic 302개와 agentic 92개는 카탈로그 검증 범위입니다. Heavy 75개는 전부 실행한 것이 아니며, RVX 한 과제의 준비와 export를 실제 공개 bundle로 확인했습니다. 해결되지 않은 submodule이 있는 저장소는 준비를 거부합니다. 공식 evaluator 점수는 산출하지 않았습니다. EDA mock의 값은 모의 자료이며 측정 모드 캐시에 재사용하지 않습니다. 외부 반입은 파일 무결성과 대응 관계를 확인한 주장으로 표시하며 원본 실행을 인증하지 않습니다.

문서 교정은 새/수정된 가이드 문단 35개(7,308자)를 대상으로 했습니다. `artifacts/docs-t007/_workspace/2026-11-07-001-9230/`에 원문·윤문본·gate를 보존했습니다. Light 경로는 별도 진단/finalizer 승급 없이 monolith 역할과 gate를 수행하며, Worker 역할 제약에 따라 순차 fallback을 사용했습니다. 연결어미 뒤 쉼표 3곳만 제거했고 수치·조건·코드·기존 교정 본문을 보존했습니다. 변경률이 낮아 이미 간결한 글로 판단했습니다.

원자료와 screenshot/PDF는 `artifacts/`에 있으므로 Git source bundle에는 포함되지 않습니다. 재현 증거를 반입할 때는 해당 실행 디렉터리 전체 또는 `repo-transfer`/`eda-export` 산출물을 함께 전달합니다. 새 실행은 항상 새 출력 디렉터리를 사용합니다. 다음 초기 기록은 당시 검증 이력이며 현재 확장 검증 수치와 구분합니다.

---

# 초기 구현 기록 (v0.1)

저장소에 보존한 증거: [검증 결과 JSON](validation/validated-v0.1.json). 실제 검증 기록에서 작업 폴더의 절대경로만 `<workspace>`로 치환했으며, 소스 해시와 기준·오류 구현 판정도 포함합니다.

상세 HTML·로그는 로컬 `artifacts/validated/`에 있으며 Git에는 포함하지 않습니다. 새 환경에서는 `python3 scripts/validate.py`를 실행한 뒤 출력되는 `index.html`을 열면 같은 형식의 상세 보고서를 생성할 수 있습니다.

| 검증 | 결과 |
|---|---|
| Python 자동 회귀 테스트 | 34/34 PASS |
| 자체 RTL 기준 구현 | 6/6 과제 PASS, 54 check×seed PASS |
| 자체 RTL 오류 구현 | 12/12 검출, 선언한 기능 검사 실패 확인 |
| CVDP LFSR 변형 기준 구현 | 1/1 과제 PASS, 9 check×seed PASS |
| CVDP LFSR 오류 구현 | 2/2 검출 |
| 인터넷 차단 실행 | counter 기준 PASS / 오류 2개 검출 |
| HTML 로컬 링크 | 588개 존재 확인 |
| 독립 코드 리뷰 | 발견된 결함 수정 후 완료 판정 |

실행 환경은 `artifacts/validated/*/reference/results.json`에 보존했습니다. Icarus Verilog 12.0으로 실제 RTL을 compile/simulate했으며, grader에는 bubblewrap을 사용했습니다. 인터넷 차단 시험은 부모 프로세스를 별도 network namespace에서 실행했습니다. 사내 폐쇄망 자체에서 실행한 결과는 아닙니다.

자동 테스트에는 실제 command adapter와 로컬 HTTP mock 서버 연결, 느린 응답의 전체 timeout, 잘못된 코드, 시뮬레이터 hang, 누락 제출, symlink/path traversal, 조기 종료/위조 PASS 거부, 오류와 인프라 장애 구분, testcase 변경 시 hash 변경, 보고서 증거 검증/escape/이동 후 로그 링크, HWE 결과 그룹 검증이 포함됩니다.

실제 모델 endpoint, 공식 CVDP Docker evaluator, HWE 이미지/evaluator, 상용 EDA/PPA/formal은 실행하지 않았습니다. 기준 구현 검증을 모델 점수로 해석하지 마십시오. 원래 제안한 24개 공개 과제 평가까지 완료했다는 의미도 아닙니다.

`artifacts/demo`, `artifacts/verified`, `artifacts/final-validation`, `artifacts/release-validation` 등은 개발 중간 기록입니다. 초기 구현의 최종 판단에는 **artifacts/validated**를 사용했습니다. 반입 소스 bundle은 실행 결과를 포함하지 않으므로 검증 결과를 전달할 때 `artifacts/validated/` 전체를 별도로 함께 복사하십시오.

재실행: 저장소 루트에서 `python3 scripts/validate.py`. 기존 결과를 덮어쓰지 않고 새 시간별 디렉터리를 생성합니다.
