# 구현 검증 결과

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

`artifacts/demo`, `artifacts/verified`, `artifacts/final-validation`, `artifacts/release-validation` 등은 개발 중간 기록입니다. 최종 판단에는 **artifacts/validated**를 사용합니다. 반입 소스 bundle은 실행 결과를 포함하지 않으므로 검증 결과를 전달할 때 `artifacts/validated/` 전체를 별도로 함께 복사하십시오.

재실행: 저장소 루트에서 `python3 scripts/validate.py`. 기존 결과를 덮어쓰지 않고 새 시간별 디렉터리를 생성합니다.
