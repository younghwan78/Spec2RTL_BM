module credit_counter #(parameter MAX = 8) (
  input clk, input rst,
  input consume, input ret,
  output can_send, output [$clog2(MAX+1)-1:0] credits, output overflow
);
  // Implement the specified behaviour here.
endmodule
