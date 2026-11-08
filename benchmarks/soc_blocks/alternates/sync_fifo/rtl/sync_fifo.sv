module sync_fifo #(parameter WIDTH = 8, parameter DEPTH = 4) (
  input clk, input rst,
  input wr_en, input [WIDTH-1:0] wr_data, output full,
  input rd_en, output [WIDTH-1:0] rd_data, output empty,
  output [$clog2(DEPTH+1)-1:0] count
);
  // Shift-register style: entry 0 is always the oldest.
  reg [WIDTH-1:0] s [0:DEPTH-1];
  reg [DEPTH:0] occ; // one-hot occupancy
  integer i, c;
  assign full = occ[DEPTH];
  assign empty = occ[0];
  reg [$clog2(DEPTH+1)-1:0] cv;
  always @* begin cv = 0; for (i = 0; i <= DEPTH; i = i + 1) if (occ[i]) cv = i; end
  assign count = cv;
  assign rd_data = s[0];
  wire pop = rd_en && !empty, push = wr_en && !full;
  always @(posedge clk)
    if (rst) occ <= 1;
    else begin
      if (pop) for (c = 0; c < DEPTH-1; c = c + 1) s[c] <= s[c+1];
      if (push) s[cv - pop] <= wr_data;
      if (push && !pop) occ <= occ << 1;
      if (pop && !push) occ <= occ >> 1;
    end
endmodule
