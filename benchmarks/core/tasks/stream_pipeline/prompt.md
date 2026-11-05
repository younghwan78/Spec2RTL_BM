# stream_pipeline

Implement/repair the synthesizable SystemVerilog module below. Only modify the listed RTL files. Preserve ports and functional behavior described here.

```systemverilog
module stream_pipeline(input clk,rst,in_valid, input [7:0] in_data, output in_ready, input out_ready, output out_valid, output [7:0] out_data);
```

One-entry elastic 8-bit stream register. Synchronous active-high rst clears out_valid. in_ready=!out_valid||out_ready. Data transfers on valid&&ready. Hold output data and valid while stalled. Throughput one item per clock after initial latency. Wrapper delegates to helper module elastic_stage; both files may be edited.

No testbench or simulation system tasks belong in the submitted RTL.
