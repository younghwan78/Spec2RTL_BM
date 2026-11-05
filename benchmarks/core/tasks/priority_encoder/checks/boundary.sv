`timescale 1ns/1ps
module tb;
reg [7:0] req;wire [2:0] index;wire valid;integer i,k,expect_idx;priority_encoder dut(req,index,valid);task check;begin #1;expect_idx=0;for(k=7;k>=0;k=k-1)if(req[k])expect_idx=k;if(index!==expect_idx[2:0]||valid!== (req!=0))$fatal(1,"priority mismatch req=%h",req);end endtask
integer seed; integer ignored; initial begin seed=1; ignored=$value$plusargs("SEED=%d",seed);
req=129;check;req=0;check;req=128;check;
$display("HWBENCH_PASS"); $finish; end
initial begin #100000; $fatal(1,"timeout"); end
endmodule
