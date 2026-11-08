`timescale 1ns/1ps
module tb;
integer seed, ignored, i, j, k;
reg clk = 0, rstn = 0; reg [3:0] awaddr = 0, araddr = 0, wstrb = 0; reg awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0; reg [31:0] wdata = 0;
wire awready, wready, bvalid, arready, rvalid; wire [1:0] bresp, rresp; wire [31:0] rdata;
axil_regs dut(clk, rstn, awaddr, awvalid, awready, wdata, wstrb, wvalid, wready, bresp, bvalid, bready, araddr, arvalid, arready, rdata, rresp, rvalid, rready);
always #5 clk = ~clk;
reg [31:0] m [0:3];
task send_aw(input [3:0] a, input integer d); integer c; begin repeat(d) @(negedge clk); awaddr = a; awvalid = 1; c = 0; @(posedge clk); while (awready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "awready"); @(posedge clk); end @(negedge clk); awvalid = 0; end endtask
task send_w(input [31:0] x, input [3:0] s, input integer d); integer c; begin repeat(d) @(negedge clk); wdata = x; wstrb = s; wvalid = 1; c = 0; @(posedge clk); while (wready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "wready"); @(posedge clk); end @(negedge clk); wvalid = 0; end endtask
task take_b(input integer stall); integer c; begin c = 0; while (bvalid !== 1'b1) begin @(negedge clk); c = c + 1; if (c > 80) $fatal(1, "bvalid"); end
 repeat(stall) begin @(negedge clk); #1; if (bvalid !== 1'b1 || bresp !== 2'b00) $fatal(1, "b stall"); if (awready !== 1'b0 || wready !== 1'b0) $fatal(1, "write ready during response"); end if (bresp !== 2'b00) $fatal(1, "bresp"); bready = 1; @(posedge clk); @(negedge clk); bready = 0; #1; if (bvalid !== 1'b0) $fatal(1, "bvalid not cleared"); end endtask
task write(input [3:0] a, input [31:0] x, input [3:0] s, input integer da, input integer dw, input integer stall); integer b; begin fork send_aw(a, da); send_w(x, s, dw); join take_b(stall);
 for (b = 0; b < 4; b = b + 1) if (s[b]) m[a[3:2]][8*b +: 8] = x[8*b +: 8]; end endtask
task read(input [3:0] a, input integer d, input integer stall); integer c; reg [31:0] e; begin repeat(d) @(negedge clk); e = m[a[3:2]]; araddr = a; arvalid = 1; c = 0; @(posedge clk); while (arready !== 1'b1) begin c = c + 1; if (c > 80) $fatal(1, "arready"); @(posedge clk); end @(negedge clk); arvalid = 0; c = 0;
 while (rvalid !== 1'b1) begin @(negedge clk); c = c + 1; if (c > 80) $fatal(1, "rvalid"); end
 repeat(stall) begin @(negedge clk); #1; if (rvalid !== 1'b1 || rdata !== e || rresp !== 2'b00) $fatal(1, "r stall"); if (arready !== 1'b0) $fatal(1, "read ready during response"); end if (rdata !== e || rresp !== 2'b00) $fatal(1, "rdata"); rready = 1; @(posedge clk); @(negedge clk); rready = 0; #1; if (rvalid !== 1'b0) $fatal(1, "rvalid not cleared"); end endtask
task reset_all; begin rstn = 0; repeat(3) @(posedge clk); @(negedge clk); rstn = 1; m[0] = 0; m[1] = 0; m[2] = 0; m[3] = 0; end endtask

initial begin
seed = 1; ignored = $value$plusargs("SEED=%d", seed);
reset_all; for (i=0;i<260;i=i+1) begin j = $random(seed) & 15; k = (j + 4 + (($random(seed)&1)*4)) & 15; case ($random(seed) & 3)
0: write(j, $random(seed), $random(seed), $random(seed)&3, $random(seed)&3, $random(seed)&3);
1: read(j, $random(seed)&3, $random(seed)&3);
2: fork write(j, $random(seed), $random(seed), $random(seed)&1, $random(seed)&1, $random(seed)&1); read(k, 0, $random(seed)&1); join
default: begin write(j, $random(seed), 4'hf, 0, 0, 0); read(j, 0, 0); end endcase end
$display("HWBENCH_PASS");
$finish;
end
initial begin #4000000; $fatal(1, "bench timeout"); end
endmodule
