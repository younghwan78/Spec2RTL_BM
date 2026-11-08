# 폐쇄망 EDA 평가 계약

이 경로는 기능 채점과 별도로 실행한다. 현재 검증한 것은 모의 wrapper와 파일 반입 계약이다. 실제 RTL Architect, PowerPro, lint, Xprop 명령이나 보고서 parser는 제공하지 않는다. 사내 담당자가 설치 버전과 라이브러리에 맞는 wrapper를 작성한다. 외부 서비스·다운로드·패키지 설치는 실행 과정에 없다.

## 실행 순서

```bash
python3 scripts/eda_controls.py --out artifacts/eda-control-new
python3 -m hwbench eda-plan artifacts/기능결과 --config configs/eda-mock.example.json --out artifacts/eda-queue --timeout 3600 --budget 14400
python3 -m hwbench eda-export artifacts/eda-queue --out 반입디렉터리
python3 -m hwbench eda-verify-transfer 반입디렉터리
python3 -m hwbench eda-run 반입디렉터리 --cache 사내캐시디렉터리
python3 -m hwbench eda-export 반입디렉터리 --out 결과반입디렉터리
python3 -m hwbench eda-import artifacts/eda-queue 결과반입디렉터리
python3 -m hwbench eda-report artifacts/eda-queue --out artifacts/eda-report
python3 -m hwbench eda-compare 기준큐 후보큐 --out artifacts/eda-comparison
```

`eda-mock.example.json`은 고정된 가짜 수치를 생성한다. 실제 PPA가 아니다. 실행 가능한 예제는 `eda_controls.py`이며 위 경로 이름은 운영자가 바꿔야 한다.

## 입력과 wrapper

설정은 `schema_version`, `mode`(`mock` 또는 `measured`), `stage`(`synthesis` 또는 `rtl_estimate`), `tool`의 이름·버전, `library`의 이름·corner, `effort`, `workload`의 ID·clock_period_ns·window를 요구한다. `tool.components`에는 결과에 기여한 도구별 `name`과 `version`을 기록한다. Measured 모드는 `area_delay`와 `power` 역할을 필수로 요구한다. Lint/Xprop 결과를 보고한다면 `lint`/`xprop` 역할도 추가한다. 한 도구가 여러 역할을 맡으면 같은 이름·버전을 각각 기록한다. 도구 버전을 모르면 측정 비교 설정을 완료한 것으로 처리하지 않는다.

`assets`에는 최소한 wrapper, library, constraints, workload의 로컬 파일 경로를 지정한다. 추가 스크립트·라이브러리는 자산 목록에 넣는다. 큰 라이브러리 묶음은 사내 파일 목록과 각 파일 SHA256을 담은 고정 manifest를 자산으로 넣고 wrapper가 실제 라이브러리와 대조해야 한다. 이 엔진은 manifest 외부 파일의 내용을 자동 검증하지 않는다.

`argv`는 shell 문자열이 아닌 인자 배열이다. `{asset:wrapper}`, `{request}`, `{response}`를 포함하며 추가 자산은 `{asset:이름}`으로 참조한다. Wrapper와 모든 자산 내용, argv, 명시적 환경변수 이름을 조건 hash에 넣는다. 자산 파일은 큐에 복사한다. 실행 파일 wrapper의 실행 권한도 보존한다.

`env_names`는 사내 라이선스 연결·인증용 환경변수 이름만 지정한다. 값은 저장하거나 hash하지 않는다. 결과를 바꾸는 합성 옵션·전력 옵션은 환경변수에 숨기지 말고 argv, effort 또는 고정 자산에 명시한다. Wrapper는 허용된 사내 license server만 사용해야 하며, 엔진은 네트워크 방화벽이나 agent 격리를 대신하지 않는다.

`tasks`는 요청할 task_id별 top, parameters, limits를 갖는다. Limits는 선택 사항이며 area_um2, delay_ns, power_mw의 상한이다. 목표를 주지 않은 측정은 제약 만족 여부를 `null`로 남긴다.

현재 EDA 입력은 native 채점 결과와 실제 채점 사본이다. `upstream_import` 및 repository backend는 거부한다. 기능 PASS라도 사본 hash가 다르면 거부한다. 실패·미기록·요청하지 않은 과제를 별도 상태로 남긴다. 작업 중인 agent 디렉터리를 직접 합성하지 않는다.

Wrapper는 request JSON에서 sources, assets의 경로, task_id/repeat, job_id, source_hashes, condition, input_fingerprint, condition_fingerprint를 읽는다. 이 값을 그대로 식별자로 사용하며 response JSON과 원본 보고서들을 response와 같은 디렉터리 아래에 만든다. 경로 탈출·symlink는 허용하지 않는다.

정상 response는 `scripts/eda_mock_wrapper.py`가 보여주는 구조를 따른다. 필수 값은 다음과 같다.

- `schema_version: 1`, 입력과 같은 job_id/input_fingerprint/condition_fingerprint/source_hashes/mode/stage
- `status: ok` 또는 `infra_error`, 구체적인 `reason`
- `reports`: 상대 경로별 SHA256. 원본 보고서가 없으면 반입하지 않는다.
- 정상 측정의 `metrics`: area_um2, delay_ns, power_mw. 모두 유한한 0 이상 숫자
- `units`: area_um2=`um^2`, delay_ns=`ns`, power_mw=`mW`. Wrapper가 원본 단위를 정규화한다.
- `quality`: lint와 xprop 각각 pass/fail/not_requested/infra_error. PPA와 별도 집계한다.
- `license_wait_seconds`: 측정했으면 값, 모르면 `null`
- `activity`: source_fingerprint, workload_fingerprint, report. 각 fingerprint는 정렬한 키·공백 없는 UTF-8 JSON의 SHA256이다.

여기서 area_um2는 합성 결과의 cell area 합계이며 die/core 면적이 아니다. delay_ns는 고정한 제약 아래 가장 느린 분석 경로의 data path delay이며 slack이나 주파수가 아니다. power_mw는 지정한 workload·구간의 dynamic와 leakage를 합친 평균 전력이다. Wrapper는 이 정의로 원본 도구 값을 변환하고, 추정 단계와 사용한 분석 조건을 함께 보존한다. 이 세 값만으로 signoff timing closure를 선언하지 않는다.

전력 activity는 동일한 workload로 **후보 RTL마다 새로 생성**한다. 기준 RTL의 SAIF를 후보에 재사용하지 않는다. Activity 원본도 reports에 포함한다. 제약 만족은 response의 자체 주장 대신 정규화 값과 설정 상한으로 다시 계산한다. 측정 단계가 다르면 비교하지 않는다.

## 큐·예산·중단

한 큐와 캐시는 로컬 호스트의 파일 잠금으로 한 worker만 소유한다. 기본 동시 실행 수는 1이다. 여러 호스트가 같은 네트워크 파일시스템 큐를 함께 쓰는 분산 스케줄러가 아니다. `--max-jobs`로 이번 호출의 작업 수를 줄일 수 있다.

큐는 실행 직전에 해당 작업의 허용 시간을 총예산에서 예약한다. 정상 종료하면 실제 시간으로 정산한다. Worker가 죽으면 예약액을 보존하여 재시작으로 예산이 초기화되지 않게 한다. 별도 Linux watchdog이 부모 종료를 감시하여 도구와 자식 프로세스 그룹을 종료한다. `eda-recover 큐`는 중단을 기록하고, `eda-recover 큐 --retry`만 재실행 대기열로 돌린다. 감독 프로세스가 아직 정리 중이거나 확인할 수 없는 orphan 그룹이 있으면 재시도를 거부한다. 타임아웃·실행 오류·잘못된 보고서는 원본 증거를 남긴다.

대기 시간, wrapper 실행 시간, 라이선스 대기는 다른 값이다. 총예산은 실제 wrapper 및 감독 실행에 사용한 시간이며 큐에서 기다린 시간은 제외한다. 타임아웃 감시의 짧은 polling 간격만큼 측정 시간이 예산을 넘을 수 있으며 실제 시간을 기록한다. 라이선스 대기는 wrapper가 측정하지 않으면 알 수 없다.

캐시는 동일한 입력 hash와 조건에서 성공한 로컬 wrapper 결과만 재사용한다. 원본 보고서 hash를 다시 검사한다. Mock 결과는 measured 요청에 쓰지 않으며 외부 반입 결과는 캐시에 넣지 않는다. 캐시 hit는 새 도구 실행이 아니므로 attempted에 더하지 않는다.

## 지표와 비교

보고서는 functional_planned, requested, eligible, attempted, valid_measured, valid_mock을 구분한다. 실패를 제거하지 않는다. `constraint_requested`는 목표 상한을 지정한 계획 실행 수이며, 기능 통과와 PPA 목표 만족을 모두 달성한 수를 이 분모로 나눈 값이 `function_and_ppa_rate_constrained_scope`이다. 미실행·기능 실패·측정 실패도 해당 요청 분모에 남는다.

비교는 같은 task_id/repeat, 기능 protocol, PPA 조건이 일치하는 양쪽의 유효 결과만 사용한다. 후보/기준 비율이 1보다 작으면 해당 과제의 해당 지표가 작다는 뜻이다. 기준값이 0이면 비율은 `null`이다. 누락된 결과 수와 양쪽의 전체 평가 수를 함께 보여주며 성공한 일부만으로 종합 순위를 만들지 않는다. Fixture 종류와 mode가 다른 결과는 자동 비교하지 않는다.

실행 파일의 성공 종료와 JSON 검증은 상용 도구 보고서의 의미가 맞다는 증명이 아니다. `local_wrapper`는 로컬 wrapper 실행, `externally_reported`는 파일 반입으로 전달된 주장이다. Hash는 파일 무결성 검사이며 실행 주체의 전자서명이나 원본 측정 진위 증명이 아니다. 사내 실제 연결 검증에서 기준 설계의 도구 원본 보고서와 값을 먼저 대조해야 한다.

## 측정 실행의 반입 목록 확인

`mode: measured` 작업은 실행 전에 `offline-pack`으로 만든 자료 묶음을 확인한다. `eda-run QUEUE --kit /data/kit --profile eda`를 사용한다. `eda` profile에는 tool_installation과 configuration 역할이 있어야 한다. 누락·해시·권한 불일치는 wrapper 실행 전에 거부한다. 목록 검증은 실제 도구 설치나 라이선스 checkout 검증이 아니다. 사내 설치·버전·라이선스는 별도로 확인한다. Mock control은 이 자료 없이 실행한다. 자세한 목록과 실행 절차는 `scripts/OFFLINE_CONTRACT.md`에 있다.

여러 job의 결과를 반입할 때는 모든 응답을 먼저 검사한다. 유효한 transfer 전체를 하나의 디렉터리로 설치한 뒤 queue 상태를 교체하므로, 후반 job의 잘못된 값이나 상태 저장 중단 때문에 앞선 job의 일부 파일이 재시도를 막지 않는다. Export/import의 원본과 대상 디렉터리는 서로를 포함할 수 없다.

## 사내 실제 도구에 맞추기

사용할 도구와 버전이 확정되지 않아도 시작할 수 있다. 도구 명령과 보고서 해석은 코드가 아니라 JSON 프로파일에 있다. 도구나 버전이 바뀌면 프로파일만 고친다. 프로파일은 큐 자산이므로 내용이 바뀌면 PPA 조건 hash도 바뀌어 이전 측정과 자동 비교되지 않는다. 아래 절차는 `benchmarks/eda_controls/profile_fixture`의 가짜 도구로만 검증했다. 실제 RTL Architect, PowerPro, lint 도구의 명령과 보고서 형식은 사내에서 채워야 한다.

1. **템플릿 복사.** `configs/eda-tool-profile.template.json`, `configs/eda-company.template.json`을 사내 경로로 복사한다. `REPLACE_`가 남아 있으면 wrapper와 `eda-plan`이 거부한다. 실제로 쓰는 도구의 항목만 남긴다.
2. **버전 확인.** 프로파일의 `version_probes`에 버전 명령과 버전을 잡는 정규식(capture group 1개)을 적고 실행한다. 다른 항목이 미완성이어도 동작한다. 미작성 항목은 `not_configured`로 나온다.
   ```bash
   python3 scripts/eda_calibrate.py versions --profile /data/eda/profile.json --out /data/eda/versions-r1.json
   ```
   확인한 이름과 버전을 회사 설정의 `tool.components`에 옮긴다.
3. **수동 1회 실행.** 사내 기준 설계 하나를 도구로 직접 돌려 원본 보고서를 얻는다. 합성·전력 스크립트는 자산(`synth_script` 등)으로 고정한다.
4. **파싱 규칙 작성.** `metrics`의 각 `terms`에 보고서 파일명, 값을 잡는 정규식, 정규화 단위로 바꾸는 `scale`을 적는다. 같은 패턴이 여러 번 나오면 `occurrence`(기본 마지막)로 고른다. 전력처럼 합산 값은 term을 여러 개 둔다. 단위 정의는 위 절의 area/delay/power 정의를 따른다. 예: 보고서가 uW이면 `scale: 0.001`.
5. **교정.** 사람이 원본 보고서에서 직접 읽어 정규화 단위로 환산한 값을 `expected.json`에 적고 대조한다. 도구는 실행하지 않는다.
   ```json
   {"read_by": "담당자", "reference_design": "설계명", "metrics": {"area_um2": 0, "delay_ns": 0, "power_mw": 0}, "quality": {"lint": "pass"}}
   ```
   ```bash
   python3 scripts/eda_calibrate.py reports --profile /data/eda/profile.json --reports /data/eda/ref-run \
     --expected /data/eda/expected.json --tolerance-pct 0.5 --out /data/eda/calibration-r1.json
   ```
   결과는 `calibrated`, `mismatch`, `parse_failed` 중 하나이고 프로파일·보고서 hash와 함께 남는다. `calibrated`가 아니면 측정을 시작하지 않는다.
6. **큐 연결.** 회사 설정에 `argv: ["python3", "{asset:wrapper}", "{asset:profile}", "{request}", "{response}"]`를 쓰고 `eda-plan`/`eda-run`을 실행한다. 정상 측정 전에 `measured` 모드는 `--kit`로 자료 묶음을 확인한다.
7. **재교정 조건.** 도구 버전, 보고서 형식, 프로파일, library, constraint가 바뀌면 3~5를 다시 한다.

`steps[].argv`에서 쓸 수 있는 치환자는 `{sources}`, `{filelist}`, `{top}`, `{work}`, `{params_json}`, `{clock_period_ns}`, `{workload_id}`, `{library_name}`, `{corner}`, `{effort}`, `{asset:이름}`이다. 단계 실패·시간 초과·파싱 실패는 수치 없이 `infra_error`로 남는다. 교정은 파서와 단위의 정확성만 확인한다. 합성 옵션이나 constraint가 적절한지, 측정값이 signoff 수준인지는 보증하지 않는다.
