# 폐쇄망 평가 과제와 평가 기준

이 문서는 인터넷 없이 실행하는 suite 구성과 결과 판독 기준을 정의한다. 아래 수치는 기준·오류 RTL로 확인한 채점기 검증 결과이며 모델 성능이 아니다.

## 1. 과제 구성

모든 과제는 저장소에 포함되어 있고 Python 표준 라이브러리, Icarus Verilog, 선택적 bubblewrap만 필요하다.

| Suite | 등급(tier) | 과제 수 | 구성 | 출처 |
|---|---|---:|---|---|
| `benchmarks/core` | 없음(unknown) | 6 | 소형 생성·수정 | 자체 작성 |
| `benchmarks/cvdp_adapted` | 없음(unknown) | 1 | LFSR 변형 | CVDP 변형 |
| `benchmarks/verilog_eval` | `public_small` | 134 | spec-to-RTL | VerilogEval 변형 |
| `benchmarks/rtllm` | `public_small` | 25 | spec-to-RTL | RTLLM 2.0 변형 |
| `benchmarks/public_repair` | `synthetic_repair` | 122 | 주입 결함 수정 | 위 두 suite에서 파생 |
| `benchmarks/soc_blocks` | `soc_block` / `soc_repair` | 12 / 8 | APB, AXI-Lite, AXI-Stream, CDC FIFO, ECC, CRC 등 | 자체 작성 |

- **공식 점수가 아니다.** 공개 과제의 checker는 HWBench 판정과 seed 입력에 맞게 변형했다. VerilogEval·RTLLM 공식 점수와 비교하지 않는다.
- **제외 과제는 기록한다.** 게이트를 통과하지 못한 공개 과제는 `third_party/verilog_eval/provenance.json`, `third_party/rtllm/provenance.json`의 `excluded`에 사유와 함께 있다.
- **난이도 근거가 다르다.** 공개 suite는 기준 RTL 줄 수 휴리스틱(`difficulty_basis: reference_loc_heuristic`), `soc_blocks`는 작성자 판단(`author_judgement`)이다. suite를 넘어 난이도 라벨을 합치지 않는다.
- **주입 결함은 실제 버그가 아니다.** `synthetic_repair`와 `soc_repair`는 정답에 기계적·수동으로 넣은 결함을 고치는 과제이며 실제 회귀 버그 수정 능력을 대표하지 않는다.
- **seed 민감도는 과제별로 다르다.** suite의 `seed_sensitive`가 false이면 입력이 seed와 무관하다. 조합 회로처럼 입력을 전수에 가깝게 쓰는 과제는 seed가 달라도 결과가 같을 수 있다.
- **과제 범위의 한계가 있다.** 고정 parameter의 시뮬레이션 검사이며 UVM, formal, CDC signoff, 상용 도구 호환성을 검증하지 않는다.

## 2. 과제 채택 게이트

새 과제는 `python3 -m hwbench demo --suite ...`를 통과해야 평가에 쓴다.

1. 기준 RTL이 모든 check × seed를 통과한다.
2. starter가 기능적으로 실패한다.
3. mutant 2개 이상이 정상 컴파일 후 선언한 check의 모든 seed에서 기능 실패한다. 컴파일 오류는 검출로 치지 않는다.
4. `python3 -m hwbench audit-checkers --suite ...`에서 `weak`가 없어야 한다. 기준 RTL의 출력 하나를 상수로 고정하거나 모든 출력을 관측값 하나로 고정한 구현이 통과하면 해당 checker는 약한 것으로 판정한다. 공개 과제 중 이 조건에 걸린 과제는 제외했다. 이 감사를 통과해도 checker가 완전하다는 뜻은 아니다.
5. checker는 공개 명세만으로 기대값을 도출한다. 구조가 다른 구현이 통과해야 한다. `benchmarks/soc_blocks/alternates`의 5개 대체 구현이 회귀 테스트로 이를 확인한다. 나머지 과제는 이 확인을 하지 않았다.

사내 RTL 과제는 추가로 정답 노출 경로(RAG, 학습, Git 이력)를 차단하고, white-box checker를 쓸 때는 유지해야 할 계층과 신호명을 명세에 적는다.

## 3. 평가 수준

아래 순서로 읽는다. 앞 단계가 성립하지 않으면 뒤 단계를 해석하지 않는다.

| 수준 | 질문 | 위치 | 규칙 |
|---|---|---|---|
| L0 유효성 | 계획한 실행이 다 됐는가 | `missing_runs`, `infra_errors` | 인프라 오류·미기록이 있으면 평가 미완료로 표시하고 분모를 유지 |
| L1 기능 성공 | 전체 check × seed를 통과했는가 | `subgroups.tier` 등 | 성공률 = PASS 실행 / 계획 실행. **등급별로만 보고**하고 등급 합산 순위를 만들지 않음 |
| L2 영역별 강약 | 어디서 강하고 약한가 | `category`, `domain`, `difficulty` | 고유 과제 수가 작으면 구간이 넓으므로 함께 표시 |
| L3 불확실성 | 얼마나 믿을 수 있는가 | `pass_rate_ci95` | Wilson 95% 구간, n은 **고유 과제 수**. 반복·seed는 표본이 아님 |
| L4 실패 원인 | 왜 실패했는가 | `failure_causes` | 가장 앞 단계 원인 하나로 분류: `invalid_submission`, `compile_error`, `compile_timeout`, `simulation_timeout`, `output_limit`, `functional_mismatch`, `agent_timeout`, `agent_error`, `infra_error` 등 |
| L5 근접도 | 얼마나 가까웠는가 | `diagnostics` | check×seed 통과 비율, 일부 통과 실행 수, seed 의존 실행 수. **성공률에 반영하지 않음** |
| L6 안정성 | 반복해도 같은가 | `repeat_consistency` | `all_pass` / `mixed` / `never_pass`. pass@k가 아님 |
| L7 비교 | 구성 A가 B보다 나은가 | `comparison.json`의 `paired` | 같은 protocol의 과제 단위 짝비교와 exact 부호 검정. 인프라 오류·미기록 과제 제외. 다중 비교 보정 전 p값 |
| L8 RTL 품질 | 통과한 RTL이 쓸 만한가 | `hwbench quality` | 기능 PASS 사본만 측정. latch, combinational loop, lint 경고, repair patch 크기. 기능 성공률과 합치지 않음 |
| L9 PPA | 면적·속도·전력은 | `eda-*` | 기능 PASS 사본만, 동일 tool/version/library/constraint/workload 조건에서만 비교 |
| L10 비용 | 시간과 사용량은 | `timing`, `usage` | 관측값만 집계. 미측정은 0이 아니라 null |

## 4. 비교 설계와 필요 규모

과제를 짝지어 비교할 때, 결과가 갈리는 과제가 30%이고 α=0.05, 검정력 80%이면 성공률 20%p 차이에 약 57개, 10%p 차이에 약 234개의 고유 과제가 필요하다(정규 근사). 등급 하나의 과제 수로 판단한다. 예를 들어 `soc_block` 12개만으로는 작은 차이를 판별할 수 없다.

## 5. 권장 실행 순서

```bash
python3 -m hwbench doctor
python3 scripts/validate.py                       # 게이트 전체 재확인

# 구성별로 suite마다 새 디렉터리에 실행
for s in soc_blocks verilog_eval rtllm public_repair; do
  python3 -m hwbench run --suite benchmarks/$s/suite.json \
    --config configs/my-agent.json --repeats 3 --agent-timeout 900 \
    --sandbox required --out artifacts/agentA-$s
done

python3 -m hwbench compare artifacts/agentA-soc_blocks artifacts/agentB-soc_blocks --out artifacts/cmp-soc
python3 -m hwbench quality artifacts/agentA-soc_blocks \
  --suite benchmarks/soc_blocks/suite.json --sandbox required --out artifacts/quality-agentA-soc
```

Blind 평가에서는 `export` 산출물만 격리 환경으로 넘긴다. `reference/`, `mutants/`, `alternates/`, `checks/`는 넘기지 않는다.

`quality`의 Yosys·Verilator는 선택 도구이다. 없으면 `not_run`이고, `tool_rejected`는 공개 프런트엔드의 한계일 수 있어 설계 불량으로 판정하지 않는다.
