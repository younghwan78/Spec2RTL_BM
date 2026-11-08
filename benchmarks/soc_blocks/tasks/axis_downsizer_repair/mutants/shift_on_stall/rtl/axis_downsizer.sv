module axis_downsizer (
  input clk, input rst,
  input s_valid, output s_ready, input [31:0] s_data, input [3:0] s_keep, input s_last,
  output m_valid, input m_ready, output [7:0] m_data, output m_last
);
  reg [31:0] d;
  reg [2:0] left;
  reg last;
  wire have = left != 0;
  wire beat = have && m_ready;
  assign m_valid = have;
  assign m_data = d[7:0];
  assign m_last = last && left == 1;
  assign s_ready = !have || (left == 1 && m_ready);
  always @(posedge clk)
    if (rst) left <= 0;
    else if (s_valid && s_ready) begin
      d <= s_data;
      left <= s_keep[3] ? 3'd4 : s_keep[2] ? 3'd3 : s_keep[1] ? 3'd2 : 3'd1;
      last <= s_last;
    end
    else if (have) begin d <= d >> 8; left <= left - 1; end
endmodule
