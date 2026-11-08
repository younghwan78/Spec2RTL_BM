module credit_counter #(parameter MAX = 8) (
  input clk, input rst,
  input consume, input ret,
  output can_send, output [$clog2(MAX+1)-1:0] credits, output overflow
);
  reg [$clog2(MAX+1)-1:0] n;
  reg ov;
  wire take = consume;
  assign can_send = n != 0;
  assign credits = n;
  assign overflow = ov;
  always @(posedge clk)
    if (rst) begin n <= MAX; ov <= 0; end
    else if (take && !ret) n <= n - 1'b1;
    else if (!take && ret) begin
      if (n == MAX) ov <= 1;
      else n <= n + 1'b1;
    end
endmodule
