# CVDP 폐쇄망 연결

이 경로는 반입한 파일만 읽는다. 인터넷 다운로드, Git 원격 갱신, Docker pull, 패키지 설치를 실행하지 않는다. `catalog-lock.json`은 공개 데이터셋 revision `5b807d945f6a99aa645f7e43a64a2115e281b4bf`의 no-commercial 파일 세 개를 SHA256으로 고정한다. 원문과 라이선스·NOTICE는 함께 반입한다. 카탈로그의 469개는 nonagentic 302개, agentic 92개, Heavy 75개다. 이 수량이 실행 완료 수나 spec-to-RTL만의 과제 수를 뜻하지는 않는다. `catalog.json`의 category/difficulty/track으로 평가 집합을 정한다.

## 외부에서 준비하고 사내에서 확인할 파일

- 고정 revision의 JSONL 세 개. `cvdp-catalog`가 이름·해시·개수를 검사한다.
- Heavy의 `context.repo`에 해당하는 `<repo>.bundle`. 공개 배포 디렉터리는 `cvdp_v1.1.0_agentic_heavy_code_generation_public`이다.
- 공식 evaluator 소스와 revision, 필요한 Docker 이미지의 save archive와 digest, 이미지 안에 설치한 모든 Python/OS 의존성. 사내에서는 미리 load한 이미지와 로컬 파일만 사용한다.
- 사내 agent wrapper와 모델 endpoint 설정. 평가 대상 agent는 trusted harness, 원본 데이터의 해답, 채점 저장소에 접근하지 못하게 운영자가 격리한다.

HWBench source bundle만으로 공식 Heavy 평가 환경이 완성되지는 않는다. `prepared.json`의 readiness는 **저장소 준비만 완료**를 뜻하며 evaluator/image 실행 가능성을 확인하지 않는다. `cvdp-prepare`는 bundle 또는 commit이 없으면 중단한다. 해결되지 않은 Git submodule이 있으면 조용히 생략하지 않고 중단한다. 필요한 하위 저장소가 완전히 포함된 sanitized baseline인지 사외 준비 단계에서 확인한다. 원래 개발 저장소의 `origin.commit` 대신 공개 sanitized `context.commit`을 사용한다.

## 사내 실행 순서

```bash
python3 -m hwbench cvdp-catalog --datasets /data/cvdp --out artifacts/catalog
python3 -m hwbench cvdp-prepare \
  --dataset /data/cvdp/cvdp_v1.1.0_agentic_heavy_code_generation_no_commercial.jsonl \
  --bundles /data/cvdp/bundles --tasks cvdp_agentic_heavy_rvx_0004 \
  --out artifacts/rvx-prepared
python3 -m hwbench repo-export --prepared artifacts/rvx-prepared --out artifacts/rvx-work
# 별도 격리 환경에서 agent가 rvx-work 안의 허용 파일을 수정한다.
python3 -m hwbench repo-submit --prepared artifacts/rvx-prepared \
  --submissions artifacts/rvx-work --out artifacts/rvx-submission
```

`--tasks`를 생략하면 Heavy 전체를 준비하므로 필요한 bundle 모두를 반입해야 한다. export는 baseline과 공개 prompt만 내보낸다. Git 이력은 baseline 한 개의 새 root commit이며 remote가 없다. `patch`의 값이 비어 있어도 정답으로 채우지 않는다. key만 수정 허용 경로로 사용하므로 `.md`처럼 RTL 이외의 허용 파일도 보존한다. 제출에서는 허용되지 않은 파일의 추가·삭제·내용 변경과 심볼릭 링크를 거부한다. 실행 권한은 baseline 권한으로 정규화한다. `prepared`는 채점 운영자가 보호해야 하는 신뢰 자료다. 해시는 전자서명이 아니다.

명시적으로 설정한 로컬 wrapper로 agent를 실행하려면 다음 명령을 쓴다. 이 명령 자체는 agent를 격리하지 않는다. 실패나 timeout이 있으면 자동 submission을 만들지 않으며 계획 ID·실행 로그를 보존한다. 실패 작업 디렉터리를 `repo-submit`으로 다시 제출하는 것은 운영자의 별도 수동 평가다.

```bash
python3 -m hwbench repo-run --prepared artifacts/rvx-prepared \
  --config /data/config/repository-agent.json --timeout 600 --out artifacts/agent-run
```

## 공식 evaluator 연결 계약

`repo-evaluate`는 운영자가 작성한 wrapper를 argv로 실행한다. 예시는 `configs/repository-evaluator.example.json`이다. `isolation: operator_managed_container`와 `offline: true`는 운영자의 실행 계약 선언이며, HWBench가 Docker 설정을 대신 검사하거나 격리를 자동 구성하지는 않는다. Wrapper는 고정 evaluator와 사전 load한 이미지로 실행하고 pull/build 다운로드 및 외부 네트워크를 금지해야 한다. 데이터셋 안의 harness Python을 host에서 직접 실행하면 안 된다.

```bash
python3 -m hwbench repo-evaluate --prepared artifacts/rvx-prepared \
  --submission artifacts/rvx-submission --config /data/config/repository-evaluator.json \
  --kit /data/kit --profile heavy --timeout 3600 --out artifacts/rvx-evaluation
# 별도 사내 채점기에서 응답 파일을 반입한 경우
python3 -m hwbench cvdp-import --prepared artifacts/rvx-prepared \
  --submission artifacts/rvx-submission --response /data/result/response.json \
  --out artifacts/rvx-imported
```

Wrapper는 `{request}` JSON을 받고 `{response}`에 정규화된 JSON을 쓴다. Request에는 trusted prepared 경로, frozen submission 경로, 두 fingerprint, expected_ids, 응답 경로가 있다. 응답에는 다음 필드가 필요하다.

```json
{
  "schema_version": 1,
  "prepared_fingerprint": "request의 값",
  "submission_fingerprint": "request의 값",
  "evaluator_revision": "고정 evaluator revision",
  "image_digest": "sha256:64자리 실제 이미지 해시",
  "protocol_id": "고정된 evaluator 실행 설정 식별자",
  "reports": {"raw/report.json": "원본 파일 SHA256"},
  "tasks": [{
    "task_id": "계획된 task ID",
    "status": "pass",
    "reason": "원본의 개별 과제 판정 근거",
    "source_hashes": {"파일경로": "submission.json의 해당 과제 해시"}
  }]
}
```

모든 계획 ID가 정확히 한 번 필요하다. 판정하지 못한 과제도 `missing`, `unresolved`, `infra_error`, `timeout`으로 명시한다. 원본 report는 응답 파일의 하위 경로에 두고 해시를 제공한다. 허용 상태는 `pass`, `fail`, `infra_error`, `timeout`, `missing`, `unresolved`다. Import는 파일 무결성과 ID 대응을 확인하고 **외부에서 보고한 결과**로 표시한다. 원본 실행을 재검증하지 않으며 공식 raw report parser도 아니다. Category 집계 비율, passing_tests 수, pass@k 수치만으로 개별 과제 PASS를 만들어서는 안 된다.

## 사외 검증 범위

```bash
python3 scripts/repository_controls.py --out artifacts/repository-controls-new
```

이 명령은 로컬 Git bundle을 만들고, baseline·정답·오류 RTL을 실제 Icarus와 required sandbox에서 검증한다. 작은 저장소 기반 채점 경로의 control이며 공식 Heavy 난이도나 모델 능력 점수가 아니다. `repo-grade`도 이 fixture 전용이고 공식 Heavy dataset에는 적용되지 않는다. `scripts/repository_external_fixture.py`는 외부 JSON 응답 계약만 검증하며 항상 `unresolved`를 반환한다. 공식 Docker evaluator와 실제 모델 실행은 별도 사내 검증 항목이다.

출처: [공식 evaluator 설명](https://github.com/NVlabs/cvdp_benchmark/blob/main/README_AGENTIC.md), [고정 데이터셋 revision](https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset/tree/5b807d945f6a99aa645f7e43a64a2115e281b4bf).

## 반입 목록과 실행 기록 보강

실제 Heavy `repo-evaluate`에는 `--kit /data/kit --profile heavy`를 함께 지정한다. 이 profile에는 evaluator와 image_archive 역할이 필요하며, wrapper 시작 전에 파일의 해시·권한·집합을 검증한다. 자료 확인은 이미지 load나 도구 설치 확인과 다르다. `scripts/OFFLINE_CONTRACT.md`의 목록 예시와 반입 검증 절차를 따른다.

`repo-run`은 모든 계획 과제의 실패·timeout·미판정을 표준 results.json/report.html에도 기록한다. 정상 agent 종료는 기능 PASS가 아니라 `unresolved`다. Frozen submission의 실행 권한도 baseline/default와 비교하며, chmod로 실행 동작을 바꾸면 결과 반입을 거부한다. 완전한 결과 반입에는 `repo-transfer`와 `repo-verify-transfer`를 사용해 prepared·submission·evaluation을 함께 보존한다.
