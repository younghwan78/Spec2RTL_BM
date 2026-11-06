# HWBench — 폐쇄망 이관용 RTL 평가 시작 패키지

Python 표준 라이브러리와 Icarus Verilog로 실행하는 작은 HW 설계 평가기입니다. 설치형 Python 패키지 의존성이 없으며 **이 저장소 루트에서 명령을 실행**하면 됩니다. 모델/harness는 연결 설정으로 교체하고, 최종 RTL은 별도 작업 공간에서 공통 채점합니다.

**현재 범위:** 자체 RTL 6과제와 CVDP LFSR 변형 1과제의 native 채점, 계획 분모·난이도·반복·실패 단계 집계, command/HTTP 연결, HWE 결과 반입을 지원합니다. CVDP no-commercial 469개 카탈로그 검사와 Heavy 저장소 준비·외부 evaluator 연결, 기능 PASS 후 별도 EDA 큐·캐시·결과 반입, 폐쇄망 자원 목록 검증도 제공합니다. 실제 상용 EDA·공식 CVDP 전체 평가·실제 모델 성능은 아직 검증하지 않았습니다.

처음 읽는 분은 [평가 목적·지표·비교·운영 가이드](docs/guide/index.html)를 여십시오. 외부 자원 없이 열리는 단일 HTML이며 계산 예시, Heavy/PPA 해석과 반입 절차를 설명합니다.

## 1. 가장 빠른 실행

요구 환경: Linux, Python 3.10 이상, `iverilog`, `vvp`. `bubblewrap`이 있으면 RTL compile/simulation의 파일 시스템과 네트워크 격리를 자동 사용합니다. Ubuntu/Debian의 패키지명은 `iverilog`, `bubblewrap`입니다. Verilator/Yosys는 버전 기록만 하며 현재 기능 채점에 필수는 아닙니다.

```bash
python3 -m hwbench doctor
python3 scripts/validate.py
```

마지막에 출력되는 `artifacts/validation-<UTC시간>/index.html`을 브라우저로 여십시오. 네트워크 없이 열립니다. 자동 테스트, 정답/오류 RTL 실제 시뮬레이션, CVDP 변형 예제, 가능한 환경에서는 전체 프로세스의 인터넷 차단 검증까지 실행합니다. 필수 런타임을 사전에 설치했다면 최초 실행에도 패키지 다운로드가 필요 없습니다. Git과 bubblewrap이 있는 환경에서는 원래 checkout을 마운트하지 않은 새 경로에서 native·저장소·EDA mock·반입을 검증합니다.

정답 100%와 오류 구현 0%는 **채점기 검증**입니다. 모델 성능 점수가 아닙니다. 모든 결과의 종류를 보고서에 표시합니다.

## 2. 사내 모델 평가: HTTP 연결

`configs/openai-compatible.example.json`을 복사하여 `base_url`과 `model`을 변경합니다. `base_url`은 보통 `/v1`까지 포함합니다. 이 adapter는 OpenAI-compatible **Chat Completions 단발 응답**을 사용하며 도구 호출 agent는 아닙니다. 모델이 정확한 JSON 파일 응답을 생성해야 합니다.

```bash
cp configs/openai-compatible.example.json configs/my-model.json
# configs/my-model.json의 endpoint/model/revision/quantization 편집
python3 -m hwbench run --config configs/my-model.json --out artifacts/my-model-r1
```

인증이 필요하면 설정에 `"api_key_env": "INTERNAL_MODEL_KEY"`를 넣고 해당 환경변수를 지정하십시오. 키를 JSON 파일에 직접 넣지 않습니다. 모델 revision, 양자화, harness 버전은 실제 값으로 기록합니다. 설정 예제는 어떤 서비스에도 자동 연결되지 않습니다.

```bash
python3 -m hwbench run --config configs/my-model.json --repeats 3 \
  --agent-timeout 300 --check-timeout 10 --seeds 1,7,42 \
  --out artifacts/my-model-3repeats
```

HTTP 연결은 로컬 mock 서버로 검증했습니다. 실제 사내 모델 및 인증 endpoint는 아직 검증하지 않았습니다. 재시도나 best-of 선택을 자동 수행하지 않습니다. 모델의 유효하지 않은 JSON은 제출 실패, 통신 오류는 인프라 오류로 기록합니다.

## 3. Codex·Claude Code·OpenCode 등 agent 연결

`configs/command.example.json`의 `argv`를 회사에서 사용하는 headless 실행 wrapper로 설정합니다. 특정 harness의 인증/버전별 플래그를 임의로 고정하지 않았습니다.

Wrapper 계약:

- 인자 `{workspace}`와 `{prompt}`는 절대경로, `{task_id}`는 과제 ID로 치환됩니다.
- 현재 작업 디렉터리는 해당 과제 workspace입니다.
- `prompt.md`와 starter RTL을 읽고 허용된 RTL 파일을 수정한 뒤 종료합니다.
- shell 해석 없이 argv 배열로 실행합니다. `$VAR`, `~`, pipe 등의 자동 확장은 없습니다.
- stdout/stderr, 종료 코드, 시간 초과를 기록합니다. 종료 후 공통 채점기가 RTL을 별도 디렉터리로 복사합니다.
- command adapter의 token/API 비용은 자동 추정하지 않습니다. 제공되지 않은 값은 미측정입니다.

```bash
python3 -m hwbench run --config configs/my-agent.json --out artifacts/my-agent-r1
python3 -m hwbench compare artifacts/my-model-r1 artifacts/my-agent-r1 --out artifacts/comparison
```

단발 모델과 agent는 다른 실행 protocol로 분류됩니다. 비교 보고서는 같은 protocol fingerprint와 결과 종류끼리만 묶으며, 다른 집단을 통합 순위로 만들지 않습니다.

**보안 경계:** command adapter 자체는 host 프로세스를 실행합니다. 작업 디렉터리를 바꿨다고 agent가 정답/테스트를 읽을 수 없게 되는 것은 아닙니다. 실제 blind BM은 아래 export 방식으로 문제만 별도 머신/사용자/컨테이너에 제공하고 채점 저장소는 접근시키지 마십시오. 생성된 RTL에 대한 bubblewrap은 agent 격리를 대신하지 않습니다. HDL 무결성 필터 역시 악의적인 HDL 전체에 대한 보안 증명은 아닙니다.

## 4. 폐쇄망·서로 다른 실행 서버: export → grade

```bash
python3 -m hwbench export --out artifacts/prompts
```

`artifacts/prompts/<task_id>/`에는 명세, starter RTL, 허용 파일 목록만 있습니다. `reference/`, 오류 구현, hidden checker는 제외됩니다. 이 디렉터리만 agent에 전달합니다. 처리 후 `<task_id>/rtl/...` 형태를 유지한 제출물을 채점 서버로 가져옵니다.

```bash
python3 -m hwbench grade --submissions /path/to/returned-submissions \
  --label 'model-A + harness-B' --out artifacts/imported-r1 --sandbox required
```

파일 응답을 JSONL로 주고받을 때 각 줄의 형식은 `{"id":"task_id","files":{"rtl/file.sv":"전체 RTL 문자열"}}`입니다.

```bash
python3 -m hwbench import-files --responses /path/to/responses.jsonl --out artifacts/submissions
python3 -m hwbench grade --submissions artifacts/submissions --out artifacts/offline-r1
```

최종 채점기는 허용된 `.v/.sv`만 복사하고 고정된 테스트를 사용합니다. 누락/심볼릭 링크/경로 탈출과 테스트 종료·출력·파일 접근을 수행하는 RTL system task를 거부합니다. 이 작은 suite에서는 include/macro 전처리도 제한하며 함수 `$clog2/$bits/$signed/$unsigned`만 허용합니다. 일반적인 대규모 RTL 전체를 위한 언어 정책은 아닙니다.

## 5. 포함 과제와 판정

| 과제 | 분류 | 주요 검사 |
|---|---|---|
| saturating_add | 생성 | overflow 경계, 65,536개 입력 조합, seeded 입력 |
| priority_encoder | 생성 | 우선순위, 모든 request mask, no request |
| counter | 수정 | hold, wrap, reset 우선순위 |
| fifo | 수정 | 순서, full/empty, 동시 입출력, occupied reset |
| stream_pipeline | 작은 다중 파일 수정 | backpressure, 데이터 보존, reset |
| round_robin | 작은 다중 파일 수정 | grant 선택, 수락 시 우선순위 갱신, fairness |

고정 폭의 작은 제어 회로입니다. 상용 저장소 탐색 난도, UVM, CDC/RDC, parameter 조합 전체, PPA, formal을 대표하지 않습니다. 조합 회로 일부는 exhaustive 입력 검사이며 순차 회로는 경계+seeded scoreboard 검사입니다. 코드/기능 coverage 수치는 측정하지 않습니다.

**과제 PASS = 모든 필수 check × seed 통과.** 컴파일 성공, 시뮬레이터 정상 종료, 정확히 한 번의 신뢰된 완료 표식을 모두 요구합니다. seed 반복을 독립 과제로 세지 않습니다. timeout/잘못된 코드/빈 제출은 실패, 실행 도구 누락/통신 장애는 인프라 오류입니다. 총점의 분모는 계획 실행 수를 유지하고 인프라 오류·미실행이 있으면 미완료를 표시합니다. 수동 재실행은 새 디렉터리로 수행하고 원래 기록을 보존합니다.

## 6. 보고서

각 실행 디렉터리에 다음을 생성합니다.

- `report.html`: 업무별 결과, 과제/check/seed, 실패 로그, agent 시간/usage, 실제 명령과 tool exit, 도구 버전, 해시.
- `report.md`: 검토용 텍스트 보고서.
- `results.json`: 원본 실행·판정 기록. 로그 경로는 실행 디렉터리 기준 상대경로.
- `tasks.csv`, `checks.csv`, `summary.json`: 비교·후처리.
- `tasks/<id>/submission/`: 실제로 채점한 RTL 사본과 각 check의 로그.

```bash
python3 -m hwbench report artifacts/my-model-r1
python3 -m hwbench list
```

새 모델/harness 비교에서는 같은 suite·체커 hash, seed, 제한시간, simulator, 실행 모드를 유지하십시오. 생성 평가는 순차 실행이며 GPU 병렬 부하의 영향은 자동 측정하지 않습니다. EDA는 별도 직렬 큐에서 관리합니다. API usage는 서비스 반환값이고 실행 시간은 측정된 경과 시간입니다. tokenizer 간 직접 비용 등가나 사내 GPU 비용을 임의 계산하지 않습니다.

## 7. CVDP·HWE 연결 범위

**CVDP:** NVIDIA 공개 v1.1.0 LFSR 예제와 원본 harness를 `third_party/cvdp/example.jsonl`에 보존했습니다. 출처·SHA256·라이선스·NOTICE도 포함합니다. `benchmarks/cvdp_adapted`는 동일 명세/기준 RTL을 이용하되 native Icarus checker로 변형했습니다. 모든 비영 초기값의 비트 단위 전이, 255개 고유 상태, 비동기 reset을 검증합니다. 공식 Docker evaluator 점수와 동등성을 주장하지 않습니다.

```bash
python3 -m hwbench demo --suite benchmarks/cvdp_adapted/suite.json --out artifacts/cvdp-demo
python3 -m hwbench run --suite benchmarks/cvdp_adapted/suite.json \
  --config configs/my-model.json --out artifacts/cvdp-model
```

**HWE:** 실제 10GB Ibex 이미지와 공식 evaluator는 이번 설치/실행 범위에 포함하지 않았습니다. 공식 `final_report.json`의 네 ID 그룹을 검증해 통합 보고서로 가져오는 기능을 제공합니다. Harbor stub reward를 읽지 않습니다.

```bash
python3 -m hwbench import-hwe /path/to/final_report.json \
  --label 'hwe-ibex-model-A' --dataset-id 'ibex-PINNED_REVISION' \
  --expected-ids /path/to/expected_ids.json --out artifacts/hwe-import
```

`expected_ids.json`은 고정 데이터의 과제 ID 문자열 배열입니다. 생략하면 task membership 검증을 하지 않았음을 표시합니다. 가져온 보고서는 실행을 재검증하거나 서명 검증한 결과가 아닙니다. 상세 upstream 로그와 버전은 별도로 보존해야 합니다. [공식 실행 안내](https://github.com/pku-liang/hwe-bench/blob/main/docs/agents.md)를 따르십시오.

## 8. 반입 패키지

```bash
python3 -m hwbench bundle --out artifacts/hwbench-offline.tar.gz
python3 -m hwbench verify-bundle artifacts/hwbench-offline.tar.gz
```

소스, 과제, 테스트, 문서, 예제 설정과 파일별 해시를 묶습니다. 바이너리·Python runtime·상용 EDA·실제 실행 결과/모델 키는 포함하지 않습니다. 사내 OS에 맞는 Python/Icarus/bubblewrap 패키지는 별도 준비합니다. 기존 결과를 전달할 때는 해당 실행 디렉터리 전체를 복사하십시오. `configs/`에 사내 설정을 추가한 뒤 bundle하면 그 설정도 포함되므로 반입 전에 내용을 확인하십시오.

사내에서는 먼저 `doctor`, `scripts/validate.py`로 동일 기준 판정을 확인한 뒤 모델을 연결합니다. `bundle`에는 루트 AGENTS.md도 포함되지만 바이너리와 외부 데이터셋은 포함되지 않습니다.

## 9. 보강한 지표

`run`과 `grade`는 첫 실행 전에 `task_plan`을 저장합니다. 전체 성공률뿐 아니라 category/difficulty/backend별 성공률도 계획 실행 수를 분모로 사용합니다. 예전 결과에 계획 목록이 없으면 분류별 계획 수·비율은 `null`이며, 기록된 결과의 비율은 `recorded_pass_rate`로 구분합니다. 난이도가 선언되지 않은 과제는 `unknown`입니다.

`summary.json`에는 과제별 반복 일관성, 실패 단계, 생성·채점 시간의 관측 수/합계/평균, token 관측량도 있습니다. Compile 시간은 task/repeat/check마다 한 번만 셉니다. 반복 일관성은 pass@k가 아니며 미측정 usage·비용을 0으로 만들지 않습니다. 비교 결과는 `comparison.html`과 `comparison.json`에 남습니다.

## 10. CVDP Heavy 저장소 연결

고정 공개 revision의 no-commercial 카탈로그는 nonagentic 302개, agentic 92개, Heavy 75개입니다. 앞의 두 트랙은 카탈로그 검증 범위이고 Heavy는 로컬 sanitized bundle을 통한 준비·제출·외부 evaluator 연결 범위입니다. 카탈로그 수를 평가 완료 수로 읽지 마십시오. 실제 RVX 한 과제의 준비/export와 로컬 Git/RTL control을 검증했습니다. 해결되지 않은 submodule이 있는 저장소는 준비를 거부합니다.

```bash
python3 scripts/repository_controls.py --out artifacts/repository-controls-r1
python3 -m hwbench cvdp-catalog --datasets /data/cvdp --out artifacts/catalog-r1
python3 -m hwbench cvdp-prepare \
  --dataset /data/cvdp/cvdp_v1.1.0_agentic_heavy_code_generation_no_commercial.jsonl \
  --bundles /data/cvdp/bundles --tasks cvdp_agentic_heavy_rvx_0004 \
  --out artifacts/rvx-prepared-r1
python3 -m hwbench repo-export --prepared artifacts/rvx-prepared-r1 --out artifacts/rvx-work-r1
```

Agent에게는 새 baseline 이력과 공개 prompt만 줍니다. Hidden harness는 채점 측에 보존합니다. `repo-run`은 agent 실패·timeout·기능 미판정도 표준 보고서에 남기며 정상 종료를 PASS로 만들지 않습니다. `repo-submit`, `repo-evaluate`, `cvdp-import`의 실행 계약과 완전한 결과 반입은 [Heavy 운영 계약](third_party/cvdp/OFFLINE_BRIDGE.md)에 설명했습니다. 외부 응답은 원본 보고서·제출 해시를 대조한 주장으로 표시하며 공식 raw report parser나 실행 인증 기능으로 간주하지 않습니다.

## 11. 기능 검증 후 별도 PPA 평가

PPA 입력은 native 기능 PASS의 채점 사본입니다. Repository/upstream PASS는 현재 EDA 입력으로 받지 않습니다. 예제는 **모의 값**을 생성하므로 상용 도구 없이 실행 관리 기능을 확인할 수 있습니다.

```bash
python3 scripts/eda_controls.py --out artifacts/eda-control-r1
python3 -m hwbench eda-plan artifacts/native-result-r1 \
  --config /data/company-eda.json --out artifacts/eda-queue-r1 --timeout 3600 --budget 14400
python3 -m hwbench eda-run artifacts/eda-queue-r1 \
  --kit /data/kit --profile eda --cache /data/eda-cache --max-jobs 1
python3 -m hwbench eda-report artifacts/eda-queue-r1 --out artifacts/eda-report-r1
```

첫 명령만 독립 실행 예제입니다. 나머지 native 결과·회사 설정·kit는 사내에서 준비합니다. 실제 RTLA/PowerPro/lint/Xprop 명령과 원본 보고서 parser는 설치 버전에 맞는 wrapper가 필요합니다. [EDA 계약](scripts/EDA_CONTRACT.md)에 필수 도구별 버전, library/PVT, constraints, activity, 단위, 입력·응답 JSON과 큐 복구 절차를 적었습니다.

기본 동시 실행 수는 1입니다. 최종 제출물만 실행하고 timeout·총예산·잠금·중단 후 정리·캐시를 적용합니다. `eda-compare`는 같은 kind/protocol과 PPA 조건의 task/repeat 쌍만 비교하며 누락 수를 공개합니다. 기능 계획·EDA 요청·기능 통과·실행 시도·유효 측정을 구분하고 lint/Xprop은 별도 품질 결과로 남깁니다.

## 12. 완전한 폐쇄망 반입

[반입 계약](scripts/OFFLINE_CONTRACT.md)과 `configs/offline-resources.example.json`을 참고해 외부 준비와 사내 실행을 분리합니다. 데이터셋, Git bundle, evaluator, 의존성을 설치한 이미지 archive, OS/Python 런타임과 NOTICE를 미리 확보합니다. 회사 EDA 설치·설정은 승인된 사내 경로에서 준비합니다. 실행 중 fetch/pull/install 또는 외부 API fallback은 하지 않습니다.

```bash
python3 -m hwbench offline-pack --spec /transfer/offline-resources.json --out /transfer/kit
python3 -m hwbench offline-verify /data/kit --profile heavy
python3 scripts/offline_controls.py --out artifacts/offline-check-r1
# 실제 공개 JSONL 및 RVX bundle이 준비된 경우
python3 scripts/validate.py --cvdp-dir /data/cvdp
```

`offline-verify`의 `resources_verified`는 파일 집합·해시·권한을 확인했다는 뜻입니다. 런타임 설치·이미지 load·라이선스 동작은 `not_checked`로 남으므로 사내에서 별도 확인합니다. Wrapper의 `offline` 선언은 네트워크 격리 자체가 아닙니다. 외부 접속을 막고 지정된 내부 모델 endpoint와 라이선스 서버만 허용하는 운영 정책이 필요합니다.

저장소 증거는 `repo-transfer`/`repo-verify-transfer`, EDA 큐는 `eda-export`/`eda-verify-transfer`/`eda-import`로 전달합니다. 출력 디렉터리는 원본과 분리하고 새 경로를 사용합니다. [최신 검증 기록](docs/VALIDATION.md)에 실제로 확인한 범위와 미실행 항목을 구분했습니다.
