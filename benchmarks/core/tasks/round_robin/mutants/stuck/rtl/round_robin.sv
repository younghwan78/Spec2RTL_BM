module round_robin(input clk,rst,accept, input [1:0] req, output [1:0] grant);
reg pref; choose_grant u(req,pref,grant); always @(posedge clk) if(rst)pref<=0;else if(accept&&|grant)pref<=0;
endmodule
