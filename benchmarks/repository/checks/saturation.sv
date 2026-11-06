module tb;
reg [3:0] a,b;
wire [3:0] y;
integer i,j,expected;
top dut(.a(a),.b(b),.y(y));
initial begin
 for(i=0;i<16;i=i+1) begin
  for(j=0;j<16;j=j+1) begin
   a=i; b=j; #1; expected=i+j; if(expected>15) expected=15;
   if(y !== expected[3:0]) $fatal(1,"saturation mismatch");
  end
 end
 $display("HWBENCH_PASS"); $finish;
end
endmodule
