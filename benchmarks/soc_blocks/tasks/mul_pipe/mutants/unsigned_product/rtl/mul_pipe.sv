module mul_pipe (
  input clk, input rst, input en, input in_valid,
  input signed [15:0] a, input signed [15:0] b,
  output out_valid, output signed [31:0] p
);
  reg [15:0] a_r, b_r;
  reg signed [31:0] p1, p2;
  reg v1, v2, v3;
  assign p = p2;
  assign out_valid = v3;
  always @(posedge clk)
    if (rst) begin v1 <= 0; v2 <= 0; v3 <= 0; end
    else if (en) begin v1 <= in_valid; v2 <= v1; v3 <= v2; end
  always @(posedge clk)
    if (en) begin a_r <= a; b_r <= b; p1 <= a_r * b_r; p2 <= p1; end
endmodule
