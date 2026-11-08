module rr_arbiter #(parameter N = 4) (
  input clk, input rst,
  input [N-1:0] req, input lock, input accept,
  output [N-1:0] grant
);
  // Implement the specified behaviour here.
endmodule
