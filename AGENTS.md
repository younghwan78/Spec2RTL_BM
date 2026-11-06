# AGENTS.md

## 프로젝트 목적과 적용 범위

이 저장소의 주요 목적은 **SoC HW IP를 개발하는 폐쇄망 환경에서 agent 기반 spec-to-RTL 벤치마크를 수행하고, agent별·model별 성능 차이를 재현 가능한 근거로 판별하는 것**이다. 기능을 추가하거나 평가 방식을 바꿀 때는 평가의 정확성, 비교의 공정성, 폐쇄망 실행 가능성을 우선한다.

이 문서는 저장소 전체를 유지보수하는 에이전트의 작업 지침이다. 평가 대상 에이전트에 제공하는 문제 명세는 각 과제의 `prompt.md`와 export 산출물이다. 벤치마크 개발 권한과 평가 대상의 접근 권한을 혼동하지 않는다.

- 사용자 설명과 운영 문서는 기본적으로 한국어로 작성한다. 코드 식별자, CLI, 데이터 필드와 기존 과제의 언어는 일관성을 유지한다.
- 변경 전 관련 코드와 테스트를 읽고, 기존 사용자 변경과 실행 증거를 보존한다.
- 실행하지 않은 평가, 지원하지 않는 도구, 측정하지 않은 지표를 완료되었거나 검증된 것으로 표현하지 않는다.

## 현재 구현

- Linux, Python 3.10 이상, Python 표준 라이브러리 기반 CLI이다. 저장소 루트에서 `python3 -m hwbench`로 실행하며 패키지 설치는 필수가 아니다.
- 기능 채점에는 `iverilog`와 `vvp`를 사용한다. `bubblewrap` 사용 가능 시 compile/simulation을 격리한다. Verilator/Yosys는 현재 버전 기록 대상이며 기능 채점 엔진이 아니다.
- 기본 suite는 `benchmarks/core/suite.json`이다. 생성 2과제(`saturating_add`, `priority_encoder`), 수정 2과제(`counter`, `fifo`), 작은 다중 파일 수정 2과제(`stream_pipeline`, `round_robin`)가 있다.
- `benchmarks/cvdp_adapted`에는 공개 CVDP LFSR 예제 1과제를 native Icarus checker로 변형한 suite가 있다. 공식 CVDP evaluator 점수와 동일하지 않다.
- HWE는 공식 `final_report.json`의 결과 가져오기를 지원한다. 공식 evaluator와 Ibex 이미지 실행은 구현 검증 범위에 포함되지 않는다.
- 현재는 작은 고정 폭 RTL의 순차 실행 벤치마크이다. UVM, CDC/RDC, 전체 parameter 조합, formal, 합성/PPA, 상용 EDA signoff를 검증했다고 간주하지 않는다.

## 코드 위치와 실행 흐름

| 위치 | 책임 |
| --- | --- |
| `hwbench/cli.py` | CLI, fixture demo, 오프라인 bundle 생성·검증 |
| `hwbench/common.py` | suite 로딩·해시, 경로 검증, 프로세스 제한시간, 도구 버전, sandbox |
| `hwbench/execution.py` | 문제 export, 제출 JSON 파싱, command/HTTP adapter, 반복 실행 |
| `hwbench/http_worker.py` | HTTP 호출을 별도 프로세스로 실행하여 전체 제한시간 적용 |
| `hwbench/grader.py` | 제출 RTL 검사·사본 보존, 독립 compile/simulation, check·seed 판정 |
| `hwbench/reporting.py` | 결과 증거 검증, 집계, HTML/Markdown/JSON/CSV, 비교 그룹 |
| `hwbench/upstream.py` | HWE 결과 가져오기와 task ID 검증 |
| `benchmarks/*/suite.json` | 과제 목록, 허용 RTL 파일, checker, 오류 구현의 예상 실패 |
| `benchmarks/*/tasks/` | `prompt.md`, `starter/`, `reference/`, `checks/`, `mutants/` |
| `tests/` | `unittest` 기반 엔진·adapter·보고서 회귀 테스트 |
| `scripts/validate.py` | 회귀 테스트, 정답·오류 RTL, CVDP 변형, 가능한 환경의 인터넷 차단 검증 |
| `third_party/cvdp/` | 보존한 원본 예제, provenance, 라이선스·NOTICE |
| `docs/VALIDATION.md`, `docs/validation/` | 기존 검증 범위와 보존 증거 |
| `docs/goals/rtl-benchmark/` | 초기 구현의 완료된 작업 기록; 현재 구현 여부는 코드와 실행 증거로 확인 |
| `artifacts/` | 실행 결과·로그·보고서. Git 추적 제외 |

일반 실행은 `suite 로딩 → prompt/starter export → adapter 실행 → 허용 RTL 사본 보존 → 독립 채점 → 보고서` 순서이다. 폐쇄망 분리 운영에서는 `export → 별도 환경의 agent 실행 → import-files 또는 제출 디렉터리 반입 → grade`를 사용한다.

## Agent·model 비교 원칙

1. **평가 단위를 구분한다.** Model은 이름·revision·양자화 등으로 식별하고, agent/harness는 이름·버전·wrapper·허용 도구·실행 예산으로 식별한다. 하나의 실행 구성은 이들의 조합이다.
2. **비교 변수를 통제한다.** Model 차이를 볼 때는 harness와 도구·예산을 고정하고, agent 차이를 볼 때는 model과 추론 설정을 고정한다. 둘 다 달라지면 조합 간 차이로 보고하며 특정 요소의 효과라고 단정하지 않는다.
3. **문제와 채점 조건을 고정한다.** Suite/과제 부분집합, 명세·starter·checker, seed 목록, simulator/runner, sandbox, 제한시간, 반복 횟수를 비교 전에 정한다. Prompt나 checker 변경은 새로운 평가 조건이다.
4. **실행 protocol을 구분한다.** `type: openai`는 Chat Completions 단발 응답이며 도구 호출 agent가 아니다. `type: command`는 외부 headless agent wrapper 실행이다. 다른 protocol을 하나의 순위로 합치지 않는다.
5. **설정과 증거를 보존한다.** 지원 필드인 `model`, `model_revision`, `quantization`, `harness`, `harness_version`, `temperature`, `max_tokens`, `seed`, `notes`에 실제 값을 기록한다. 추가 도구 권한·context/token 예산·재시도 정책 등은 `notes`나 별도 실험 기록으로 남긴다. 미지원 항목이 자동 수집된다고 가정하지 않는다.
6. **자동 그룹화의 범위를 안다.** 현재 `compare`는 동일 `protocol_fingerprint`와 `kind`끼리 묶는다. Wrapper 내부의 도구·재시도·예산 정책까지 검사하지 않으므로 같은 그룹이라는 사실만으로 모든 조건이 같다고 판단하지 않는다.
7. **모든 계획 실행을 집계한다.** 실패를 제거하거나 성공한 반복만 선택하지 않는다. 현재 성공률은 PASS 실행 수 / 계획 과제 실행 수이며, seed별 check를 독립 과제로 세지 않는다. `--repeats`는 생성 반복, `--seeds`는 RTL 검증 입력 seed이며 모델 생성 `seed`와 다르다. 반복 성공률을 자동으로 pass@k라고 부르지 않는다.
8. **실패와 미측정을 구분한다.** 잘못된 RTL·빈 제출·제한시간 초과는 성공이 아니다. 도구 누락·통신 장애는 인프라 오류로 별도 기록하고 분모를 유지한다. Command adapter의 token/API 비용, 사내 GPU 비용 등 미측정 값은 0으로 만들거나 추정하지 않는다.
9. **주장을 증거 수준에 맞춘다.** 정답·오류 fixture 결과는 채점기 검증이며 model 성능이 아니다. 소수 과제의 결과를 전체 SoC IP 설계 능력으로 일반화하지 않는다. 속도·usage는 기능 성공률과 함께 해석하고, 반복 수와 평가 범위를 명시한다.

## 명세·RTL·checker 작성 규칙

- 명세에는 포트와 폭, signedness, clock/reset 극성·동기 여부·우선순위, latency/throughput, handshake, stall/hold, overflow, 경계·동시 동작, 정의되지 않은 값과 지원 parameter 범위를 명시한다. 해당하지 않는 항목은 억지로 추가하지 않는다.
- Checker는 공개 명세로부터 기대 동작을 도출해야 한다. 기준 RTL의 내부 구현이나 명세에 없는 동작을 정답 조건으로 강요하지 않는다. 명세가 모호하면 평가 전에 명확히 하고 변경된 조건으로 다시 실행한다.
- 제출물은 허용된 `.v`/`.sv` 파일만 사용하고 포트 계약을 유지한다. 테스트벤치 제어, 완료 표식 위조, 파일 접근 등으로 판정을 우회하지 않는다.
- 과제에는 `prompt.md`, 허용 파일에 대응하는 `starter/`와 `reference/`, 독립 `checks/`, 의도적인 오류 `mutants/` 및 suite 항목을 갖춘다. 현재 `demo`는 과제마다 최소 2개 mutant와 기능적으로 실패하는 starter를 요구한다.
- 정답 구현은 모든 필수 check × seed를 통과해야 한다. Mutant는 정상 컴파일된 뒤 선언한 `expected_fail_checks`에서 기능 오류로 검출되어야 한다. 컴파일 오류나 인프라 장애만으로 검출 성공이라 하지 않는다.
- 각 checker 소스에는 `HWBENCH_PASS` 완료 표식이 정확히 한 번 있어야 한다. 채점기는 이를 실행별 표식으로 치환한다. PASS에는 정상 compile/simulation 종료와 정확히 한 번의 완료 표식이 필요하다.
- 현재 제출 RTL의 system function 허용 목록은 `$clog2`, `$bits`, `$signed`, `$unsigned`이며 include/macro 등 전처리와 테스트벤치 간섭도 제한한다. 실제 IP 지원을 위해 완화할 때는 무결성 검사·격리·테스트를 함께 검토한다.
- `benchmarks/core/build_fixtures.py`와 `scripts/prepare_cvdp_example.py`는 과제 파일을 덮어쓰는 생성기이다. 일상 검증 목적으로 실행하지 않는다. 생성된 과제 수정 시 생성기와의 불일치를 확인하고, 재생성할 경우 기존 수정을 잃지 않는지 diff를 검토한다.

## 폐쇄망과 평가 데이터 격리

- 기본 실행·검증·보고서 열기에 인터넷, CDN, 원격 패키지 다운로드를 요구하지 않는다. Python 런타임 의존성은 표준 라이브러리를 유지하고, 의존성 추가가 필요하면 오프라인 반입·설치 방법을 함께 마련한다.
- 사내 spec, RTL, 제출물, 로그를 외부 서비스로 전송하지 않는다. 모델 실행은 사용자가 지정한 허용 endpoint와 wrapper로 수행하며 외부 API로 자동 fallback하지 않는다.
- API 키는 설정 파일의 평문 값 대신 `api_key_env`로 참조한다. 키와 내부 인증 정보를 코드·로그·보고서·bundle에 포함하지 않는다.
- 실제 blind 평가에서는 `export` 산출물만 평가 대상에게 제공한다. `reference/`, `mutants/`, hidden `checks/`, 채점 저장소와 기존 정답 로그는 별도 환경에서 보호한다. 유지보수 중의 접근 권한을 평가 대상에게 넘기지 않는다.
- Command adapter는 host 프로세스이다. Workspace 변경만으로 agent가 격리되지 않는다. Bubblewrap은 생성된 RTL의 compile/simulation 격리이며 agent 격리를 대체하지 않는다. HDL 필터 역시 적대적 제출물에 대한 완전한 보안 보장이 아니다.
- 격리가 필수인 채점에는 `--sandbox required`를 사용한다. 사용할 수 없으면 원인을 기록하고 필수 조건을 조용히 `off`로 낮추지 않는다.
- `third_party/` 원본, 출처·revision·SHA256, 라이선스와 NOTICE를 보존한다. 변형 결과는 공식 upstream 점수와 구분한다.
- Bundle에는 runtime/EDA 바이너리와 `artifacts/` 결과가 포함되지 않는다. `configs/`는 포함되므로 내부 설정의 포함 여부를 확인한다. 현재 `hwbench/cli.py`의 bundle 목록에는 루트 `AGENTS.md`가 없으므로 이 지침이 필요한 반입에서는 별도로 함께 전달한다.

## 작업과 검증

모든 명령은 저장소 루트에서 실행한다. 변경 범위에 맞는 검증을 선택하고, 기존 결과를 덮어쓰지 않는 새 출력 디렉터리를 사용한다.

```bash
# 환경과 기본 suite 확인
python3 -m hwbench doctor
python3 -m hwbench list

# Python 로직, adapter, 보고서 회귀 검증
python3 -m unittest discover -s tests -v

# 기본 과제의 정답·오류 구현을 실제 시뮬레이션
python3 benchmarks/core/verify.py

# 전체 검증: 자동으로 새 artifacts/validation-<UTC시간>/ 생성
python3 scripts/validate.py
```

- 문서만 바꿀 때는 실제 코드·CLI와 지침의 일치 여부, 경로·명령, `git diff --check`를 확인한다. 불필요한 테스트를 추가하지 않는다.
- 실행·채점·결과 형식 변경에는 해당 회귀 테스트를 실행한다. 판정·timeout·무결성 경계의 버그를 수정할 때는 실제 실패를 재현하는 테스트를 보강한다.
- RTL·명세·checker 변경에는 정답과 mutant 검증을 수행한다. CVDP 변형을 수정하면 해당 suite의 `demo`도 실행한다.
- 채점 의미, 여러 모듈 또는 반입 경로에 영향을 주는 변경은 `scripts/validate.py`로 통합 검증한다. Bubblewrap 미지원에 따른 인터넷 차단 시험 생략을 성공으로 표현하지 않는다.
- 실제 모델 평가가 필요하면 example config를 토대로 사내 설정을 준비한다. Placeholder나 로컬 HTTP mock의 성공을 실제 모델 연결 검증으로 보고하지 않는다.
- 결과의 `results.json`, 채점한 RTL 사본, 로그, hash, 도구 버전을 함께 보존한다. 수동 재실행은 새 디렉터리에 남기고 원래 실패 기록을 수정하지 않는다.
- 기존 `docs/VALIDATION.md`의 수치는 당시 검증 기록이다. 새 실행을 대신하지 않으며, 새 결과를 기록할 때 실행 명령·경로·제한사항을 함께 남긴다.
- 최종 보고에는 변경 내용, 실행한 검증과 결과, 미실행 항목을 간결하게 명시한다. CLI나 결과 의미를 변경했다면 `README.md` 등 해당 사용 문서도 갱신한다.

## 확장 방향

추가 개발은 실제 SoC IP 명세를 반영한 과제 확대, 사내 agent/model 연결, 반복 실험과 비교 근거 개선을 중심으로 진행한다. Lint·합성·PPA·formal·상용 EDA를 도입할 때는 기능 점수와 별도 지표로 정의하고, 동일한 tool/version/constraint/library 조건 및 미실행 상태를 기록한다. 기능적 정확성이 확인된 RTL을 대상으로 PPA를 비교한다. 이 항목들은 향후 방향이며 현재 구현된 기능 목록이 아니다.
