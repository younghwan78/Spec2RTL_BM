# 폐쇄망 반입과 검증

`offline-pack`은 운영자가 지정한 로컬 파일·디렉터리만 복사한다. `offline-verify`는 상대 경로, 파일 집합, SHA256, 크기와 권한을 확인한다. 큰 이미지·패키지도 스트림으로 해시한다. 다운로드·설치·Docker pull은 실행하지 않는다. 해시는 전자서명이 아니므로 반입 목록 자체도 신뢰할 수 있는 경로로 전달한다.

## 외부 준비와 사내 실행

외부 준비 단계에서 고정 revision의 데이터셋과 sanitized Git bundle, evaluator 소스, 라이선스·NOTICE, 컨테이너 이미지와 런타임 패키지를 확보한다. Docker 이미지는 필요한 의존성을 모두 넣어 `docker save`로 보존하고, OS 패키지·Python wheel은 사내 OS/Python 버전에 맞춘다. 사내에서는 승인한 설치 절차, `docker load -i images.tar`, 필요 시 `pip install --no-index --find-links /data/wheels ...`를 사용한다. HWBench가 이 명령을 자동 실행하지는 않는다.

```bash
python3 -m hwbench bundle --out /transfer/hwbench-source.tar.gz
python3 -m hwbench verify-bundle /transfer/hwbench-source.tar.gz
# configs/offline-resources.example.json을 복사해 실제 로컬 경로와 revision으로 작성한다.
python3 -m hwbench offline-pack --spec /transfer/offline-resources.json --out /transfer/kit
# kit 디렉터리를 승인된 방법으로 반입한 뒤
python3 -m hwbench offline-verify /data/kit --profile heavy
```

`profiles`는 실행별 필수 resource ID 목록이다. `resources`의 각 항목은 `id`, `role`, 로컬 `path`, kit 내부 상대 `destination`을 갖는다. 파일에는 `expected_sha256`을 추가해 기존 고정 해시와 대조할 수 있다. 전체 목록의 파일을 검증하므로 kit 안에 실행 결과를 쓰지 말고 별도 출력 디렉터리를 쓴다. 심볼릭 링크·경로 이탈·겹친 destination·원본 안의 출력 디렉터리는 거부한다. 중간 구성에 빠진 파일을 네트워크에서 보충하지 않는다.

성공 상태는 **resources_verified**이며, 런타임은 **not_checked**다. 이미지 archive가 있다는 사실은 Docker에 load됐다는 뜻이 아니다. 설치 목록 파일이 있다는 사실도 실제 EDA가 설치·라이선스 checkout됐다는 뜻이 아니다. 운영자는 사내에서 Python·Git·Icarus·vvp·bubblewrap, Docker daemon/이미지, EDA 설치·PDK/library·라이선스를 별도로 확인한다. `python3 -m hwbench doctor`는 native 도구 확인에 사용한다. EDA의 정확한 버전 확인 명령과 vendor 보고서 해석은 사내 wrapper에서 검증한다.

실제 Heavy wrapper에는 `--kit /data/kit --profile heavy`가 필수다. 선택 profile에 evaluator와 image_archive 역할이 있어야 한다. 측정 모드의 `eda-run`은 `--kit /data/kit --profile eda`가 필수이며 tool_installation과 configuration 역할을 요구한다. 측정 계획의 library/constraint/workload/wrapper 파일 해시는 별도로 고정된다. 두 실행 모두 wrapper 시작 전에 목록을 확인한다. 로컬 fixture와 mock EDA는 상용 도구나 Docker 자료 없이 실행한다.

```bash
python3 -m hwbench repo-evaluate --prepared /data/prepared --submission /data/submission \
  --config /data/evaluator.json --kit /data/kit --profile heavy --out artifacts/heavy-run
python3 -m hwbench eda-run /data/eda-queue --kit /data/kit --profile eda
```

`offline: true`나 `operator_managed_container`는 wrapper의 선언이다. HWBench가 임의 wrapper의 네트워크를 자동 격리하지는 않는다. 사내 운영 정책에서 외부 접속을 막고, 명시한 내부 모델 endpoint와 라이선스 서버만 허용해야 한다. 인증 값은 환경변수로 전달하며 반입 파일에 넣지 않는다.

## 저장소 결과를 재현하는 반입 단위

`results.json`과 HTML만 옮기면 frozen source와 hidden harness가 빠진다. `repo-transfer`는 prepared baseline/harness, frozen submission, 외부 응답·원본 보고서·wrapper 실행 기록을 함께 복사한다. 채점 운영자용 자료이므로 blind 평가 agent에게 제공하지 않는다.

```bash
python3 -m hwbench repo-transfer --prepared artifacts/prepared --submission artifacts/submission \
  --evaluation artifacts/evaluation --out artifacts/reproduction-kit
python3 -m hwbench repo-verify-transfer /data/reproduction-kit
python3 -m hwbench cvdp-import --prepared /data/reproduction-kit/prepared \
  --submission /data/reproduction-kit/submission \
  --response /data/reproduction-kit/evaluation/response.json --out artifacts/reimported
```

`--evaluation`에는 response.json, 응답이 참조한 모든 raw report, wrapper-execution.json이 있어야 한다. 과거 request/argv에 기록된 절대 경로는 당시 실행 증거이며 새 경로에서 재실행하는 명령이 아니다. 다시 실행할 때는 새 경로로 wrapper 요청을 생성한다. 반입 검증은 외부 판정의 진위를 인증하거나 공식 evaluator를 재실행하지 않는다.

`repo-run`은 실패·timeout을 포함한 모든 계획 과제를 표준 results.json/report.html에 남긴다. Agent가 정상 종료해도 기능 검사를 하기 전에는 `unresolved`다. 자동 submission은 모든 agent 실행이 정상 종료한 경우에만 만든다. 실패 실행을 제거하고 성공 실행의 evaluator 결과만 비교해서는 안 된다. 실패 workspace를 수동 재제출하면 별도의 평가 실행으로 기록한다.

## 이식 검증

```bash
python3 scripts/offline_controls.py --out artifacts/offline-check-new
# 실제 공개 자료도 함께 확인할 때만 명시한다.
python3 scripts/offline_controls.py --out artifacts/offline-cvdp-new --cvdp-dir /data/cvdp
python3 scripts/validate.py
```

첫 명령은 source bundle을 새 위치에 풀고 native·Git/RTL·EDA mock·저장소 결과 반입을 검증한다. Bubblewrap에는 시스템 도구와 옮긴 자료만 마운트한다. 원래 checkout/artifacts는 보이지 않고 네트워크도 차단한다. Python·simulator 등 설치된 시스템 도구는 읽기 전용으로 사용하므로 OS 패키지 설치까지 검증한 것은 아니다. 선택한 CVDP 자료가 있으면 469개 catalog와 RVX 한 과제의 준비·export도 확인한다. 공식 Docker evaluator·실제 모델·상용 PPA는 실행하지 않는다.
