module sync_fifo #(parameter WIDTH = 8, parameter DEPTH = 4) (
  input clk, input rst,
  input wr_en, input [WIDTH-1:0] wr_data, output full,
  input rd_en, output [WIDTH-1:0] rd_data, output empty,
  output [$clog2(DEPTH+1)-1:0] count
);
  reg [WIDTH-1:0] mem [0:DEPTH-1];
  reg [$clog2(DEPTH)-1:0] wp, rp;
  reg [$clog2(DEPTH+1)-1:0] n;
  wire w = wr_en && (!full || rd_en);
  wire r = rd_en && !empty;
  assign full = n == DEPTH;
  assign empty = n == 0;
  assign count = n;
  assign rd_data = mem[rp];
  always @(posedge clk)
    if (rst) begin n <= 0; wp <= 0; rp <= 0; end
    else begin
      if (w) begin mem[wp] <= wr_data; wp <= (wp == DEPTH-1) ? 0 : wp + 1; end
      if (r) rp <= (rp == DEPTH-1) ? 0 : rp + 1;
      n <= n + w - r;
    end
endmodule
