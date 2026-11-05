# NVIDIA CVDP attribution and adaptation

Source: [NVlabs/cvdp_benchmark](https://github.com/NVlabs/cvdp_benchmark), v1.1.0 example `cvdp_copilot_lfsr_0001`.

`example.jsonl` is preserved without edits. `provenance.json` records source URLs and SHA256 of downloaded files. Repository LICENSE and dataset LICENSE/NOTICE are retained in this directory. Dataset non-code is CC BY 4.0; code follows the component terms in those files. Preserve all notices during transfer.

Adaptation: `scripts/prepare_cvdp_example.py` materializes the prompt/reference and adds independently authored native SystemVerilog checks plus intentionally incorrect controls. This does not use the official Docker/cocotb evaluation route and is NOT an official CVDP score. No NVIDIA endorsement is implied.
