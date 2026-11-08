`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg [7:0] d = 0; wire [12:0] cw; reg [12:0] rx = 0; wire [7:0] q; wire sec, ded;
secded_codec dut(d, cw, rx, q, sec, ded);
function [12:0] enc(input [7:0] v); reg [3:0] c; reg o; begin
 c[0] = v[0]^v[1]^v[3]^v[4]^v[6]; c[1] = v[0]^v[2]^v[3]^v[5]^v[6]; c[2] = v[1]^v[2]^v[3]^v[7]; c[3] = v[4]^v[5]^v[6]^v[7]; o = ^{v,c}; enc = {o,c,v}; end endfunction
reg [3:0] sy; reg pe; reg [7:0] fx; reg es, ed;
task judge(input [12:0] r); begin
 sy[0] = r[8]^r[0]^r[1]^r[3]^r[4]^r[6]; sy[1] = r[9]^r[0]^r[2]^r[3]^r[5]^r[6]; sy[2] = r[10]^r[1]^r[2]^r[3]^r[7]; sy[3] = r[11]^r[4]^r[5]^r[6]^r[7]; pe = ^r; fx = r[7:0]; es = 0; ed = 0;
 if (pe && sy <= 12) begin es = 1; case (sy) 3: fx[0] = ~fx[0]; 5: fx[1] = ~fx[1]; 6: fx[2] = ~fx[2]; 7: fx[3] = ~fx[3]; 9: fx[4] = ~fx[4]; 10: fx[5] = ~fx[5]; 11: fx[6] = ~fx[6]; 12: fx[7] = ~fx[7]; default: ; endcase end
 else if (pe || sy != 0) ed = 1;
 rx = r; #1; if (q !== fx || sec !== es || ded !== ed) $fatal(1, "decode"); end endtask

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
for (i=0;i<256;i=i+1) begin d = i; #1; if (cw !== enc(d)) $fatal(1, "encode"); judge(enc(d)); for (j=0;j<13;j=j+1) begin judge(enc(d) ^ (13'd1 << j)); for (k=j+1;k<13;k=k+1) judge(enc(d) ^ (13'd1 << j) ^ (13'd1 << k)); end end
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
