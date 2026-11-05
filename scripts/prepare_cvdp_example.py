"""Materialize a pinned CVDP example with explicitly adapted native checkers.

The upstream dataset and original cocotb harness remain verbatim in third_party.
This is an integration smoke test, NOT the official CVDP evaluator.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "third_party/cvdp/example.jsonl"
row = json.loads(source.read_text())
base = ROOT / "benchmarks/cvdp_adapted"
task = base / "tasks/lfsr"
rtl = row["output"]["context"]["rtl/lfsr_8bit.sv"]
variants = {"reference": rtl,
            "starter": "module lfsr_8bit(input clock,reset,input [7:0] lfsr_seed,output wire [7:0] lfsr_out); assign lfsr_out=0; endmodule\n",
            "mutants/wrong_tap": rtl.replace("lfsr_out[6] ^ lfsr_out[0]", "lfsr_out[7] ^ lfsr_out[0]"),
            "mutants/synchronous_reset": rtl.replace("posedge clock or negedge reset", "posedge clock")}
for variant, text in variants.items():
    p = task / variant / "rtl/lfsr_8bit.sv";p.parent.mkdir(parents=True, exist_ok=True);p.write_text(text)
(task / "prompt.md").write_text(row["input"]["prompt"] + "\n\nSource: NVIDIA CVDP v1.1.0 example cvdp_copilot_lfsr_0001.\nAdaptation: native iverilog checker, not official CVDP scoring. Zero seed is outside this task's contract.\n")
prefix = '''`timescale 1ns/1ps
module tb;
reg clock=0, reset=1; reg[7:0] lfsr_seed=8'h99; wire[7:0] lfsr_out;
lfsr_8bit dut(clock,reset,lfsr_seed,lfsr_out);
always #5 clock=~clock;
reg[7:0] expected; reg[255:0] seen; integer i,s,seed,ignored;
function[7:0] nxt(input[7:0] q); begin nxt=(q>>1) ^ (q[0]?8'hb1:8'h00); end endfunction
task load(input[7:0] v); begin @(negedge clock);reset=1;lfsr_seed=v;#1;reset=0;#1;
if(lfsr_out!==v)$fatal(1,"async reset seed mismatch got=%h expected=%h",lfsr_out,v);
@(negedge clock);reset=1;end endtask
initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
'''
suffix = '''
$display("HWBENCH_PASS");$finish;end
initial begin #2000000;$fatal(1,"timeout");end
endmodule
'''
checks = {
    "transition": ('All nonzero initial states and 16 bit-exact transitions each', '''for(s=1;s<256;s=s+1)begin load(s);expected=s;for(i=0;i<16;i=i+1)begin @(posedge clock);expected=nxt(expected);#1;if(lfsr_out!==expected)$fatal(1,"transition mismatch");end end'''),
    "period": ('255 unique nonzero states and return to seed', '''load(8'h99);seen=0;for(i=0;i<255;i=i+1)begin if((^lfsr_out)===1'bx || lfsr_out===0)$fatal(1,"invalid state");if(seen[lfsr_out])$fatal(1,"early repetition");seen[lfsr_out]=1;@(posedge clock);#1;end if(lfsr_out!==8'h99 || seen[255:1]!=={255{1'b1}})$fatal(1,"period/state coverage");'''),
    "reset": ('Asynchronous reset and restart for 40 seeded inputs', '''for(s=0;s<40;s=s+1)begin expected=($random(seed)&255);if(expected==0)expected=1;load(expected);@(posedge clock);expected=nxt(expected);#1;if(lfsr_out!==expected)$fatal(1,"restart mismatch");end''')}
for name, (description, body) in checks.items():
    p = task / f"checks/{name}.sv";p.parent.mkdir(parents=True, exist_ok=True);p.write_text(prefix+body+suffix)
manifest = {"schema_version": 1, "id": "cvdp-v1.1.0-lfsr-adapted", "title": "CVDP LFSR native adapted smoke",
            "origin": "cvdp_adapted_not_official_score", "tasks": [{"id": row["id"], "category": "generation",
            "title": "CVDP 8-bit Galois LFSR (adapted)", "path": "tasks/lfsr", "files": ["rtl/lfsr_8bit.sv"],
            "checks": [{"id": name,"tb": f"checks/{name}.sv", "top": "tb", "description": desc} for name,(desc,_) in checks.items()],
            "mutants": [{"id": "wrong_tap", "path": "mutants/wrong_tap", "expected_fail_checks": ["transition"]},
                        {"id": "synchronous_reset", "path": "mutants/synchronous_reset", "expected_fail_checks": ["reset"]}],
            "upstream_id": row["id"]}]}
(base / "suite.json").write_text(json.dumps(manifest, indent=2)+"\n")
print(base / "suite.json")
