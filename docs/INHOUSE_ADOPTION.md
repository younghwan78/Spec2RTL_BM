# 사내 적용 가이드 (Claude Code로 작업할 때)

사내 폐쇄망에서 HWBench를 설치하고, 사내 모델·Claude·CLI 구성을 비교할 때 따르는 절차입니다. 각 단계의 프롬프트는 사내 Claude Code에 그대로 붙여 쓸 수 있습니다.

벤치마크의 목적은 [안내서](guide/benchmark-value.html), 지표 정의는 [평가 기준](EVALUATION_CRITERIA.md)을 참고하십시오.

## 0. 먼저 알아 둘 것

**구현 상태**

| 항목 | 상태 | 사내에서 할 일 |
|---|---|---|
| Icarus 기반 채점, 보고서, 과제 308개 | 구현·검증됨 | 설치 후 `validate.py` 재확인 |
| 사내 모델 HTTP 연결 (`type: openai`) | 로컬 mock으로만 검증 | 실제 endpoint 연결 확인 |
| Claude Code 연결 wrapper | 가짜 `claude` 실행 파일로만 검증 | 실제 연결 확인 |
| EDA 프로파일과 교정 | 가짜 도구로만 검증 | 실제 명령과 정규식 작성, 교정 |
| Xcelium·UVM 채점 | **미구현** | 9절에서 구현 |
| 사내 RTL 과제 | **미착수** | 8절 |

**Claude Code는 두 역할로 분리합니다. 이 분리가 가장 중요합니다.**

| | 개발용 Claude Code | 평가 대상 Claude Code |
|---|---|---|
| 용도 | 이 저장소를 설치·수정·운영 | 시험을 보는 대상 |
| 접근 범위 | 저장소 전체(정답, mutant, hidden checker 포함) | `export` 산출물만 |
| 위치 | 채점 서버 | 별도 사용자·컨테이너·머신의 sandbox |
| 설정 | 프로젝트 지침 사용 | 사용자 지침·메모리·MCP 차단 |

개발용 세션에서 벤치마크 과제를 풀게 하면 정답을 볼 수 있으므로 그 결과는 무효입니다. 평가 실행 전 이 저장소가 평가 환경에서 보이지 않는지 반드시 확인하십시오.

## 1. 외부에서 준비하여 반입

```bash
# 외부 개발 환경, 저장소 루트
python3 scripts/validate.py
python3 -m hwbench bundle --out /transfer/hwbench-source.tar.gz
python3 -m hwbench verify-bundle /transfer/hwbench-source.tar.gz
```

Bundle에는 소스, 과제, 테스트, 문서, 예제 설정이 들어갑니다. 바이너리, `artifacts/`, 모델 키는 들어가지 않습니다. `configs/`의 내용을 반입 전에 확인하십시오.

별도로 준비할 것은 다음과 같습니다.

- Python 3.10 이상
- Icarus Verilog 12 (`iverilog`, `vvp`). 공개 과제는 12.0으로 검증했고, VerilogEval은 13 개발판을 지원하지 않는다고 안내합니다.
- bubblewrap (권장, `--sandbox required`에 필요)
- 선택: Yosys, Verilator (`hwbench quality`용)
- 사내에 설치할 Claude Code와 그 버전 기록

## 2. 사내 설치 확인

```bash
tar -xzf hwbench-source.tar.gz -C /data/hwbench
cd /data/hwbench
python3 -m hwbench doctor
python3 scripts/validate.py    # 외부 환경 기준 약 11분
```

`validate.py`의 모든 단계가 PASS여야 합니다. bubblewrap이 없으면 일부 단계가 SKIPPED로 나오며, 이를 통과로 간주하지 마십시오.

## 3. 개발용 Claude Code 준비

**버전과 지침 파일**

```bash
claude --version
```

Claude Code는 v2.1.277부터 `CLAUDE.md`가 없을 때 `AGENTS.md`를 읽습니다. 이전 버전이면 저장소 루트에 다음 한 줄짜리 `CLAUDE.md`를 만드십시오. 세션에서 `AGENTS.md` 내용을 요약하게 하여 실제로 읽혔는지 확인합니다.

```markdown
@AGENTS.md
```

**폐쇄망 환경변수**

사내 gateway가 Anthropic Messages 형식(`/v1/messages`)을 제공할 때의 예시입니다. Bedrock·Vertex 형식이면 각 형식의 변수를 사용합니다. 실제 값은 사내 담당자에게 확인하십시오.

```bash
export ANTHROPIC_BASE_URL="https://REPLACE-internal-gateway"
export ANTHROPIC_AUTH_TOKEN="사내 발급 토큰"     # 파일에 저장하지 말 것
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
```

Anthropic은 Claude Code를 비 Claude 모델로 연결하는 구성을 지원하지 않는다고 안내합니다. 이런 구성을 평가 행렬에 넣지 마십시오.

**첫 세션 프롬프트**

```text
AGENTS.md와 docs/INHOUSE_ADOPTION.md를 읽고 저장소 구조를 요약해 줘.
폐쇄망 환경이니 인터넷 접근, 패키지 다운로드, 외부 전송은 하지 마.
python3 -m hwbench doctor를 실행하고 결과에서 누락된 도구를 알려 줘.
코드는 아직 고치지 마.
```

## 4. 평가 대상 연결

연결마다 `counter` 한 과제로 먼저 확인합니다. 실패 시 로그는 `artifacts/<이름>/tasks/`에 있습니다.

### 4.1 사내 온프레미스 모델 (단발 호출)

OpenAI 호환 Chat Completions endpoint에 한 번 질의해 RTL을 받는 방식입니다. 도구 호출 agent가 아닙니다.

```bash
cp configs/openai-compatible.example.json /data/config/model-a.json
# base_url, model, model_revision, quantization 을 실제 값으로 수정
python3 -m hwbench run --config /data/config/model-a.json --tasks counter --sandbox required --out artifacts/smoke-model-a
```

인증이 필요하면 설정에 `"api_key_env": "변수이름"`을 쓰고, 키 값은 환경변수로만 전달합니다.

### 4.2 Claude Code (agent)

`hwbench run`은 agent를 채점 서버의 host 프로세스로 실행하며 작업 공간도 저장소 옆에 있습니다. 아래 명령은 연결 확인용이고, 성적으로 쓰는 평가는 4.4절의 blind 분리 절차를 따르십시오.

제공 wrapper는 `scripts/wrappers/claude_code_agent.py`입니다. 사용자 수준 `CLAUDE.md`, 자동 메모리, MCP, slash command를 차단하고, 기본 도구를 `Read,Edit,Write,Glob,Grep`로 제한합니다.

| 환경변수 | 의미 | 기본값 |
|---|---|---|
| `HWB_CC_MODEL` | 평가할 모델 이름 또는 alias | 필수 |
| `HWB_CC_TOOLS` | 허용 내장 도구 | `Read,Edit,Write,Glob,Grep` |
| `HWB_CC_MODE` | permission mode | `acceptEdits` |
| `HWB_CC_MAX_TURNS` | 최대 턴 수 | 없음 |
| `HWB_CC_BIN` | `claude` 실행 파일 경로 | `claude` |

사내 설치 버전에 없는 옵션이 있으면 wrapper가 실패합니다. 이때 `claude --help`로 확인해 wrapper를 고치고, 고친 내용을 평가 조건으로 기록하십시오.

```bash
cp configs/claude-code.example.json /data/config/cc-opus.json
# argv의 절대 경로, model, harness_version 수정
export HWB_CC_MODEL="사내에서 쓰는 모델 이름"
python3 -m hwbench run --config /data/config/cc-opus.json --tasks counter --agent-timeout 900 --sandbox required --out artifacts/smoke-cc
```

시뮬레이터 자체 검증을 허용하려면 `HWB_CC_TOOLS`에 `Bash`를 추가합니다. 이는 **다른 평가 조건**입니다. 격리된 환경에서만 사용하고, 허용 명령을 `notes`에 기록하십시오. `--dangerously-skip-permissions`는 일회용 격리 환경이 아니면 쓰지 마십시오.

`claude -p --output-format json`의 결과는 agent 로그에 남습니다. HWBench는 이 값을 usage로 자동 집계하지 않으므로 보고서에서는 미측정으로 표시됩니다.

### 4.3 다른 CLI agent

`configs/command.example.json`을 복사하고, 다음 계약을 지키는 wrapper를 만듭니다.

- 인자는 `{workspace}`, `{prompt}` 절대 경로이고 현재 디렉터리는 workspace입니다.
- `prompt.md`를 읽어 허용된 RTL 파일을 수정하고 종료합니다.
- shell 해석이 없으므로 pipe나 `$VAR`는 wrapper 안에서 처리합니다.

Claude Code에 맡길 때의 프롬프트입니다.

```text
scripts/wrappers/claude_code_agent.py와 README 3절의 wrapper 계약을 읽고
사내 CLI "<도구 이름>"용 wrapper를 scripts/wrappers/에 만들어 줘.
도구의 headless 실행법은 `<도구> --help` 결과로 확인하고 추측하지 마.
사용자 설정·메모리를 차단하는 옵션이 있으면 사용하고, 없으면 나에게 알려 줘.
counter 과제로 확인한 뒤 변경 내용과 실행 결과를 보고해 줘.
```

### 4.4 blind 평가 분리 절차

```bash
# 채점 서버
python3 -m hwbench export --suite benchmarks/soc_blocks/suite.json --out /transfer/prompts-soc
# 평가 환경으로 전달 후, 각 과제 디렉터리에서 agent를 실행
# 결과 <task_id>/rtl/... 구조를 채점 서버로 반입
python3 -m hwbench grade --suite benchmarks/soc_blocks/suite.json --submissions /transfer/returned-soc \
  --label '<모델> + <도구>' --sandbox required --out artifacts/agentA-soc-r1
```

`export`에는 정답, mutant, hidden checker가 포함되지 않습니다. `grade`로 반입하면 agent 시간 기록이 없으므로, 시간 비교가 필요하면 별도로 기록합니다.

## 5. 실험 설계

평가를 시작하기 전에 표를 채우고 저장합니다. 도중에 조건을 바꾸면 새 실험입니다.

| 항목 | 기록 값 |
|---|---|
| 실험의 질문 (예: 사내 모델 A와 B 중 무엇이 나은가) | |
| 고정 조건: suite, seed, 제한시간, 반복 횟수, sandbox | |
| 바뀌는 변수 (하나만) | |
| 모델 이름, revision, 양자화 | |
| 도구 이름과 버전, 허용 도구, 턴·예산 제한, 재시도 정책 | |
| Temperature 등 추론 설정 | |

**비교 유형별 고정 조건**

| 비교 | 고정 | 변경 |
|---|---|---|
| 사내 모델끼리 | 단발 호출 또는 같은 CLI, 추론 설정 | 모델 |
| Claude 모델끼리 | Claude Code 버전, 도구, 예산 | 모델 |
| CLI끼리 | 모델과 추론 설정 (같은 모델을 쓸 수 있을 때만) | CLI |
| 사내 조합 대 Claude 조합 | 문제, 채점, 제한시간 | 조합 전체. 원인을 단정하지 않음 |

단발 호출과 agent 결과는 하나의 순위로 합치지 않습니다.

**권장 순서:** 작은 것부터 돌려 연결 문제를 먼저 잡습니다.

1. `counter` 한 과제
2. `soc_blocks` 20개, 반복 1회
3. `soc_blocks`, `rtllm`, `verilog_eval`, `public_repair`, 반복 3회

```bash
for s in soc_blocks rtllm verilog_eval public_repair; do
  python3 -m hwbench run --suite benchmarks/$s/suite.json --config /data/config/cc-opus.json \
    --repeats 3 --agent-timeout 900 --seeds 1,7,42 --sandbox required --out artifacts/cc-opus-$s
done
```

**사용량:** 위 네 suite는 301개 과제이므로 3회 반복 시 903회 실행입니다. 사전에 소수 과제로 비용과 시간을 가늠하십시오.

## 6. 결과 판독

```bash
python3 -m hwbench compare artifacts/cc-opus-soc_blocks artifacts/cc-sonnet-soc_blocks --out artifacts/cmp-soc
python3 -m hwbench quality artifacts/cc-opus-soc_blocks --suite benchmarks/soc_blocks/suite.json --sandbox required --out artifacts/quality-cc-opus-soc
```

Claude Code에 맡길 때의 프롬프트입니다.

```text
docs/EVALUATION_CRITERIA.md의 평가 수준 순서대로 artifacts/cmp-soc와 각 실행의 summary.json을 분석해 줘.
인프라 오류나 미기록이 있으면 먼저 알려 줘.
등급을 합산한 순위는 만들지 말고, 고유 과제 수와 95% 구간을 함께 적어 줘.
실패 과제는 failure_causes 기준으로 묶고, 대표 사례 3개는 로그로 근거를 확인해 줘.
바뀐 변수가 둘 이상이면 원인을 단정하지 마. 결과 파일은 수정하지 마.
```

결과 디렉터리는 수정하지 않습니다. 다시 돌릴 때는 새 디렉터리를 씁니다.

## 7. EDA 도구 교정

사용 도구가 확정되지 않아도 시작할 수 있습니다. 절차는 [EDA 계약의 사내 도구 맞춤 절차](../scripts/EDA_CONTRACT.md)에 있습니다. 순서는 템플릿 복사, 버전 확인, 기준 설계 수동 실행, 파싱 규칙 작성, 교정, 큐 연결입니다.

```text
scripts/EDA_CONTRACT.md의 "사내 실제 도구에 맞추기"를 읽어 줘.
configs/eda-tool-profile.template.json을 /data/eda/profile.json으로 복사하고
/data/eda/ref-run의 원본 보고서를 보며 metrics의 정규식과 scale을 작성해 줘.
단위가 불명확하면 추측하지 말고 해당 보고서 줄을 보여 주며 나에게 물어봐.
도구 명령은 내가 알려 준 것만 쓰고, 합성 옵션은 바꾸지 마.
expected.json의 값은 내가 직접 채울 테니 값을 만들어 넣지 마.
```

`expected.json`은 사람이 원본 보고서에서 읽은 값으로 채워야 교정의 의미가 있습니다. Claude Code가 파서로 얻은 값을 그대로 적으면 자기 자신과 비교하는 것입니다.

## 8. 사내 RTL로 과제 추가

**우선순위:** 버그 수정 commit, ECO commit, leaf 모듈 비우기, 상위 연결 순입니다. 자세한 기준은 평가 기준 2절을 따릅니다.

**현재 가능한 범위:** Icarus로 compile·simulate되는 블록이고, `` `ifdef `` 같은 전처리와 허용 외 system task가 RTL에 없으며, 단일 파일 testbench로 검사할 수 있어야 합니다. UVM 환경은 9절이 끝나야 쓸 수 있습니다.

**보관 위치:** 사내 suite는 이 저장소 밖의 접근 제한 경로에 둡니다. `bundle`이 `benchmarks/` 전체를 포함하기 때문입니다. `--suite /secure/path/suite.json`으로 지정할 수 있습니다.

**과제 하나의 구조** (`benchmarks/soc_blocks/suite.json`과 tasks 예시 참고)

```text
/secure/hwbench-internal/suite.json
/secure/hwbench-internal/tasks/<task>/
  prompt.md, starter/rtl/..., reference/rtl/..., checks/*.sv, mutants/<id>/rtl/...
```

각 checker에는 `HWBENCH_PASS`가 정확히 한 번 있고, 실패 시 `$fatal`로 종료해야 합니다. 각 과제에 `tier`, `domain`, `difficulty`를 선언합니다.

**버그 수정 commit을 과제로 만드는 프롬프트**

```text
AGENTS.md의 명세·RTL·checker 작성 규칙을 따라 /repo/<ip>의 commit <hash>를 repair 과제로 만들어 줘.
수정 전 파일을 starter, 수정 후 파일을 reference로 하고, 결과는 /secure/hwbench-internal에 저장해 줘.
checker는 명세로부터 기대값을 도출하고, 수정 전 코드가 정상 컴파일 후 기능 실패하는지 확인해 줘.
내부 신호 참조가 불가피하면 유지해야 할 이름을 prompt.md에 명시해 줘.
prompt.md에는 수정 방법의 힌트, 티켓 번호, 프로젝트 코드명을 넣지 마.
```

**채택 전 확인**

```bash
python3 -m hwbench demo --suite /secure/hwbench-internal/suite.json --sandbox required --out artifacts/internal-gate-r1
python3 -m hwbench audit-checkers --suite /secure/hwbench-internal/suite.json --sandbox required --out artifacts/internal-audit-r1
```

정답 전부 통과, starter와 mutant 전부 실패여야 합니다. `audit-checkers`에서 `weak`로 나온 과제는 checker를 보강하거나 제외합니다. `unsupported`는 강도를 확인하지 못했다는 뜻이므로 통과로 보지 않습니다. 평가 환경에는 이력 없는 snapshot만 제공하고, 해당 RTL이 RAG 색인에 포함되어 있지 않은지 확인합니다.

## 9. Xcelium·UVM 연결 (미구현)

사내에 Xcelium이 있으므로 실제 IP의 UVM 환경으로 채점하려면 이 작업이 필요합니다.

```text
AGENTS.md를 따라 native 채점에 Xcelium backend를 추가하고 계획을 먼저 보여 줘. 필요한 변경은 다음과 같아.
1. suite에서 시뮬레이터를 선택하고 backend는 native로 유지. protocol에 실제 시뮬레이터와 버전을 기록.
2. 제출당 elaboration 1회, test×seed 다회 실행. 과제별 제한시간과 filelist, 지원 파일 지원.
3. 신뢰된 top이 UVM_ERROR와 UVM_FATAL이 0일 때만 완료 표식을 출력.
4. inspect_rtl이 import "DPI-C"를 거부하고, 전처리·system task는 suite별 허용 목록으로 변경.
5. 라이선스 서버 접근용 sandbox 모드를 명시적으로 추가하고 결과에 기록. 조용히 sandbox를 끄지 마.
먼저 가짜 xrun으로 회귀 테스트를 만들고, 이어서 기존 counter와 fifo의 정답·mutant를 실제 Xcelium으로 돌려 Icarus 판정과 대조해 줘.
```

실제 도구 명령은 사내 설치 버전의 `xrun -help`로 확인합니다. 시뮬레이션 횟수와 라이선스 수를 먼저 계산하십시오.

## 10. 작업 규칙

- 인터넷 접근, 외부 전송, 패키지 다운로드를 하지 않습니다. 사내 명세·RTL·로그를 외부 서비스로 보내지 않습니다.
- API 키는 환경변수로만 전달합니다.
- 실패 결과를 지우거나 성공한 반복만 고르지 않습니다.
- `build_fixtures.py`, `import_public_suites.py`는 과제를 덮어쓰므로 일상 검증에 실행하지 않습니다.
- 프롬프트, checker, seed, 제한시간을 바꾸면 새 평가 조건입니다.
- Claude Code가 "완료"라고 해도 명령 실행 결과를 확인합니다. 실행하지 않은 검증을 완료로 기록하지 않습니다.

## 11. 문제 해결

| 증상 | 확인할 것 |
|---|---|
| `Required bubblewrap sandbox is unavailable` | bwrap 설치와 user namespace 허용 여부. 조용히 `--sandbox off`로 낮추지 말고 원인을 기록 |
| 시뮬레이터를 sandbox에서 못 찾음 | `iverilog`, `vvp`가 `/usr` 아래에 있어야 함 |
| Agent 상태가 `agent_error` | `artifacts/<이름>/tasks/<과제>-r1/agent.log`. wrapper 옵션과 인증 확인 |
| Agent 상태가 `timeout` | `--agent-timeout`을 조정하면 새 평가 조건 |
| 제출이 `invalid_submission` | 허용 파일 누락, 금지된 system task나 전처리 사용 |
| `infra_error`가 많음 | 도구·통신 문제. 평가 미완료이므로 원인 해결 후 새 디렉터리에서 재실행 |
| EDA 설정이 `REPLACE_ placeholders`로 거부됨 | 템플릿의 자리표시자를 모두 실제 값으로 변경 |
| 교정 결과 `mismatch` | 보고서 단위와 `scale`, `occurrence` 확인 |
| `AGENTS.md`를 따르지 않음 | `claude --version`과 `CLAUDE.md` 존재 여부, 3절 |

## 12. 완료 확인

- [ ] `validate.py` 전 단계 PASS
- [ ] 평가 환경에서 정답·checker·이 저장소가 보이지 않음을 확인
- [ ] 각 구성의 `counter` 스모크 통과 및 로그 확인
- [ ] 실험 설계표 작성·보관
- [ ] 평가 후 `compare`, `quality` 결과와 원본 실행 디렉터리 보존
- [ ] 보고서에 미실행 항목과 해석 한계 명시
